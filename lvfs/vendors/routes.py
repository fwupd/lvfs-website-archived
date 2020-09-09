#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2017 Richard Hughes <richard@hughsie.com>
#
# SPDX-License-Identifier: GPL-2.0+
#
# pylint: disable=too-few-public-methods

import os
import secrets

from collections import defaultdict
from glob import fnmatch, glob

from flask import Blueprint, request, flash, url_for, redirect, render_template, g
from flask_login import login_required
from sqlalchemy.orm import joinedload

from lvfs import app, db

from lvfs.emails import send_email
from lvfs.hash import _otp_hash
from lvfs.util import admin_login_required
from lvfs.util import _error_internal, _email_check
from lvfs.metadata.utils import _async_regenerate_remote
from lvfs.models import Vendor, Restriction, Namespace, User, Remote, Affiliation, AffiliationAction, Verfmt, Firmware
from lvfs.util import _generate_password

from .utils import _vendor_hash

bp_vendors = Blueprint('vendors', __name__, template_folder='templates')

def _count_vendor_fws_public(vendor, remote_name):
    dedupe_csum = {}
    for fw in vendor.fws:
        if fw.remote.name == remote_name:
            dedupe_csum[fw.checksum_upload_sha256] = True
    return len(dedupe_csum)

def _count_vendor_fws_downloads(vendor, remote_name):
    cnt = 0
    for fw in vendor.fws:
        if fw.remote.name == remote_name:
            cnt += fw.download_cnt
    return cnt

def _count_vendor_fws_devices(vendor, remote_name):
    guids = {}
    for fw in vendor.fws:
        if fw.remote.name == remote_name:
            for md in fw.mds:
                for gu in md.guids:
                    guids[gu.value] = 1
    return len(guids)

class VendorStat:
    def __init__(self, stable, testing):
        self.stable = stable
        self.testing = testing

def _get_vendorlist_stats(vendors, fn):

    # get stats
    display_names = {}
    for v in vendors:
        if not v.visible:
            continue
        cnt_stable = fn(v, 'stable')
        cnt_testing = fn(v, 'testing')
        if not cnt_stable and not cnt_testing:
            continue
        display_name = v.display_name.split(' ')[0]
        if display_name not in display_names:
            display_names[display_name] = VendorStat(cnt_stable, cnt_testing)
            continue
        stat = display_names[display_name]
        stat.stable += cnt_stable
        stat.testing += cnt_testing

    # build graph data
    labels = []
    data_stable = []
    data_testing = []
    vendors = sorted(list(display_names.items()),
                     key=lambda k: k[1].stable + k[1].testing,
                     reverse=True)
    for display_name, stat in vendors[:10]:
        labels.append(str(display_name))
        data_stable.append(float(stat.stable))
        data_testing.append(float(stat.testing))
    return labels, data_stable, data_testing

def _abs_to_pc(data, data_other):
    total = 0
    for num in data:
        total += num
    for num in data_other:
        total += num
    data_pc = []
    for num in data:
        data_pc.append(round(num * 100 / total, 2))
    return data_pc

@bp_vendors.route('/list/<page>')
def route_list_analytics(page):
    vendors = db.session.query(Vendor).\
                order_by(Vendor.display_name).\
                options(joinedload('fws')).all()
    if page == 'publicfw':
        labels, data_stable, data_testing = _get_vendorlist_stats(vendors, _count_vendor_fws_public)
        return render_template('vendorlist-analytics.html', vendors=vendors,
                               category='vendors',
                               title='Total number of public firmware files',
                               page=page, labels=labels,
                               data_stable=data_stable,
                               data_testing=data_testing)
    if page == 'downloads':
        labels, data_stable, data_testing = _get_vendorlist_stats(vendors, _count_vendor_fws_downloads)
        return render_template('vendorlist-analytics.html', vendors=vendors,
                               category='vendors',
                               title='Percentage of firmware downloads',
                               page=page, labels=labels,
                               data_stable=_abs_to_pc(data_stable, data_testing),
                               data_testing=_abs_to_pc(data_testing, data_stable))
    if page == 'devices':
        labels, data_stable, data_testing = _get_vendorlist_stats(vendors, _count_vendor_fws_devices)
        return render_template('vendorlist-analytics.html', vendors=vendors,
                               category='vendors',
                               title='Total number of supported devices',
                               page=page, labels=labels,
                               data_stable=data_stable,
                               data_testing=data_testing)
    return _error_internal('Vendorlist kind invalid')

@bp_vendors.route('/')
def route_list():
    vendors = db.session.query(Vendor).\
                    filter(Vendor.visible).\
                    join(User, Vendor.vendor_id == User.vendor_id).\
                    options(joinedload(Vendor.affiliations)).\
                    order_by(Vendor.display_name).\
                    all()
    return render_template('vendorlist.html',
                           vendors=vendors)

@bp_vendors.route('/admin')
@login_required
@admin_login_required
def route_list_admin():
    vendors = db.session.query(Vendor).\
                    options(joinedload(Vendor.restrictions)).\
                    order_by(Vendor.group_id).all()
    return render_template('vendorlist-admin.html',
                           category='vendors',
                           vendors=vendors,
                           page='overview')

@bp_vendors.route('/<int:vendor_id>')
def route_show_public(vendor_id):
    vendor = db.session.query(Vendor).\
                filter(Vendor.visible).\
                filter(Vendor.vendor_id == vendor_id).\
                    options(joinedload(Vendor.users),
                            joinedload(Vendor.affiliations)).first()
    if not vendor:
        flash('Failed to show vendor: No visible vendor with that group ID', 'warning')
        return redirect(url_for('vendors.route_list'), 302)
    return render_template('vendor-show.html',
                           category='vendors',
                           v=vendor,
                           page='overview')

@bp_vendors.route('/create', methods=['GET', 'POST'])
@login_required
@admin_login_required
def route_create():
    """ Add a vendor [ADMIN ONLY] """

    # only accept form data
    if request.method != 'POST':
        return redirect(url_for('vendors.route_list_admin'))

    if not 'group_id' in request.form:
        return _error_internal('Unable to add vendor as no data')
    if db.session.query(Vendor).filter(Vendor.group_id == request.form['group_id']).first():
        flash('Failed to add vendor: Group ID already exists', 'warning')
        return redirect(url_for('vendors.route_list_admin'), 302)
    if len(request.form['group_id']) > 80:
        flash('Failed to add vendor: Group ID is too long', 'warning')
        return redirect(url_for('vendors.route_list_admin'), 302)

    # use a random access token, unless running in debug mode
    if app.config.get('DEBUG', None):
        access_token = request.form['group_id'].replace('-', '_')
    else:
        access_token = secrets.token_hex(nbytes=32)

    r = Remote(name='embargo-%s' % request.form['group_id'],
               access_token=access_token,
               is_dirty=True)
    db.session.add(r)
    db.session.commit()
    v = Vendor(group_id=request.form['group_id'], remote_id=r.remote_id)
    db.session.add(v)
    db.session.commit()
    flash('Added vendor %s' % request.form['group_id'], 'info')

    # asynchronously rebuilt
    _async_regenerate_remote.apply_async(args=(r.remote_id,), queue='metadata')

    return redirect(url_for('vendors.route_show', vendor_id=v.vendor_id), 302)

@bp_vendors.route('/<int:vendor_id>/retoken', methods=['POST'])
@login_required
@admin_login_required
def route_retoken(vendor_id):
    """ Removes a vendor [ADMIN ONLY] """
    vendor = db.session.query(Vendor).filter(Vendor.vendor_id == vendor_id).first()
    if not vendor:
        flash('Failed to delete vendor: No a vendor with that group ID', 'warning')
        return redirect(url_for('vendors.route_list_admin'), 302)

    # delete files with the old access token
    fns = glob(os.path.join(app.config['DOWNLOAD_DIR'],
                            'firmware-*-{}.*'.format(vendor.remote.access_token)))
    for fn in fns:
        os.remove(fn)

    # a random string
    vendor.remote.access_token = secrets.token_hex(nbytes=32)
    vendor.remote.is_dirty = True
    db.session.commit()

    # asynchronously rebuilt
    _async_regenerate_remote.apply_async(args=(vendor.remote.remote_id,), queue='metadata')

    flash('Regenerated vendor access token', 'info')
    return redirect(url_for('vendors.route_list_admin'), 302)

@bp_vendors.route('/<int:vendor_id>/delete', methods=['POST'])
@login_required
@admin_login_required
def route_delete(vendor_id):
    """ Removes a vendor [ADMIN ONLY] """
    vendor = db.session.query(Vendor).filter(Vendor.vendor_id == vendor_id).first()
    if not vendor:
        flash('Failed to delete vendor: No a vendor with that group ID', 'warning')
        return redirect(url_for('vendors.route_list_admin'), 302)
    db.session.delete(vendor)
    db.session.commit()
    flash('Removed vendor', 'info')
    return redirect(url_for('vendors.route_list_admin'), 302)

@bp_vendors.route('/<int:vendor_id>')
@bp_vendors.route('/<int:vendor_id>/details')
@login_required
@admin_login_required
def route_show(vendor_id):
    """ Allows changing a vendor [ADMIN ONLY] """
    vendor = db.session.query(Vendor).filter(Vendor.vendor_id == vendor_id).first()
    if not vendor:
        flash('Failed to get vendor details: No a vendor with that group ID', 'warning')
        return redirect(url_for('vendors.route_list_admin'), 302)
    verfmts = db.session.query(Verfmt).all()
    return render_template('vendor-details.html',
                           category='vendors',
                           verfmts=verfmts,
                           v=vendor)

@bp_vendors.route('/<int:vendor_id>/firmware')
@login_required
@admin_login_required
def route_firmware(vendor_id):
    """ Allows changing a vendor [ADMIN ONLY] """
    vendor = db.session.query(Vendor).filter(Vendor.vendor_id == vendor_id).first()
    if not vendor:
        flash('Failed to get vendor details: No vendor with that ID', 'warning')
        return redirect(url_for('vendors.route_list_admin'), 302)

    # get all user IDs for this vendor
    stmt = db.session.query(User.user_id).\
                            filter(User.vendor_id == vendor_id).\
                            subquery()

    # get all firmware that were uploaded by these user IDs
    fws = db.session.query(Firmware).\
                           join(stmt, Firmware.user_id == stmt.c.user_id).\
                           order_by(Firmware.timestamp.desc()).limit(101).all()

    return render_template('vendor-firmware.html',
                           category='vendors',
                           fws=fws,
                           v=vendor)

@bp_vendors.route('/<int:vendor_id>/restrictions')
@login_required
def route_restrictions(vendor_id):
    """ Allows changing a vendor [ADMIN ONLY] """

    # security check
    vendor = db.session.query(Vendor).filter(Vendor.vendor_id == vendor_id).first()
    if not vendor:
        flash('Failed to get vendor details: No a vendor with that ID', 'warning')
        return redirect(url_for('vendors.route_list'), 302)
    if not vendor.check_acl('@view-restrictions'):
        flash('Permission denied: Unable to view restrictions', 'danger')
        return redirect(url_for('vendors.route_list'), 302)
    return render_template('vendor-restrictions.html',
                           category='vendors',
                           v=vendor)

@bp_vendors.route('/<int:vendor_id>/namespaces')
@login_required
@admin_login_required
def route_namespaces(vendor_id):
    """ Allows changing a vendor [ADMIN ONLY] """
    vendor = db.session.query(Vendor).filter(Vendor.vendor_id == vendor_id).first()
    if not vendor:
        flash('Failed to get vendor details: No a vendor with that group ID', 'warning')
        return redirect(url_for('vendors.route_list_admin'), 302)

    # get prefixes from existing firmware
    appstream_ids = defaultdict(int)
    for fw in vendor.fws:
        if fw.is_deleted:
            continue
        for md in fw.mds:
            prefix = md.appstream_id_prefix
            if prefix in [ns.value for ns in vendor.namespaces]:
                continue
            appstream_ids[prefix] += 1

    # try to construct something plausible from the vendor homepage
    if not appstream_ids and vendor.url:
        parts = vendor.url.split('/', maxsplit=3)
        if len(parts) >= 3:
            dotted = parts[2].rsplit('.', maxsplit=3)
            if len(dotted) >= 2:
                prefix = '{}.{}'.format(dotted[-1], dotted[-2])
                if prefix not in [ns.value for ns in vendor.namespaces]:
                    appstream_ids[prefix] = 0

    return render_template('vendor-namespaces.html',
                           appstream_ids=appstream_ids,
                           category='vendors',
                           v=vendor)

@bp_vendors.route('/<int:vendor_id>/event')
@login_required
def route_event(vendor_id):
    """ Allows changing a vendor """

    # security check
    vendor = db.session.query(Vendor).filter(Vendor.vendor_id == vendor_id).first()
    if not vendor:
        flash('Failed to get vendor details: No a vendor with that group ID', 'warning')
        return redirect(url_for('vendors.route_list'), 302)
    if not vendor.check_acl('@manage-users'):
        flash('Permission denied: Unable to view event log', 'danger')
        return redirect(url_for('vendors.route_show', vendor_id=vendor_id))
    return render_template('vendor-event.html',
                           category='vendors',
                           v=vendor, page='event')

@bp_vendors.route('/<int:vendor_id>/users')
@login_required
def route_users(vendor_id):
    """ Allows changing a vendor [ADMIN ONLY] """

    # check exists
    vendor = db.session.query(Vendor).filter(Vendor.vendor_id == vendor_id).first()
    if not vendor:
        flash('Failed to get vendor details: No a vendor with that group ID', 'warning')
        return redirect(url_for('vendors.route_list'), 302)

    # security check
    if not vendor.check_acl('@manage-users'):
        flash('Permission denied: Unable to edit vendor as non-admin', 'danger')
        return redirect(url_for('vendors.route_show', vendor_id=vendor_id))
    return render_template('vendor-users.html',
                           category='vendors',
                           v=vendor)

@bp_vendors.route('/<int:vendor_id>/oauth')
@login_required
def route_oauth(vendor_id):
    """ Allows changing a vendor [ADMIN ONLY] """

    # check exists
    vendor = db.session.query(Vendor).filter(Vendor.vendor_id == vendor_id).first()
    if not vendor:
        flash('Failed to get vendor details: No a vendor with that group ID', 'warning')
        return redirect(url_for('vendors.route_list'), 302)

    # security check
    if not vendor.check_acl('@modify-oauth'):
        flash('Permission denied: Unable to edit vendor as non-admin', 'danger')
        return redirect(url_for('vendors.route_show', vendor_id=vendor_id))
    return render_template('vendor-oauth.html',
                           category='vendors',
                           v=vendor)

@bp_vendors.route('/<int:vendor_id>/restriction/create', methods=['POST'])
@login_required
@admin_login_required
def route_restriction_create(vendor_id):
    """ Allows changing a vendor [ADMIN ONLY] """

    # check exists
    vendor = db.session.query(Vendor).filter(Vendor.vendor_id == vendor_id).first()
    if not vendor:
        flash('Failed to get vendor details: No a vendor with that group ID', 'warning')
        return redirect(url_for('vendors.route_list_admin'), 302)
    if not 'value' in request.form:
        return _error_internal('No value')
    vendor.restrictions.append(Restriction(value=request.form['value']))
    vendor.remote.is_dirty = True
    db.session.commit()
    flash('Added restriction', 'info')

    # asynchronously rebuilt
    _async_regenerate_remote.apply_async(args=(vendor.remote.remote_id,), queue='metadata')

    return redirect(url_for('vendors.route_restrictions', vendor_id=vendor_id), 302)

@bp_vendors.route('/<int:vendor_id>/restriction/<int:restriction_id>/delete', methods=['POST'])
@login_required
@admin_login_required
def route_restriction_delete(vendor_id, restriction_id):
    """ Allows changing a vendor [ADMIN ONLY] """

    # check exists
    vendor = db.session.query(Vendor).filter(Vendor.vendor_id == vendor_id).first()
    if not vendor:
        flash('Failed to get vendor details: No a vendor with that group ID', 'warning')
        return redirect(url_for('vendors.route_list_admin'), 302)
    for res in vendor.restrictions:
        if res.restriction_id == restriction_id:
            db.session.delete(res)
            break
    vendor.remote.is_dirty = True
    db.session.commit()
    flash('Deleted restriction', 'info')

    # asynchronously rebuilt
    _async_regenerate_remote.apply_async(args=(vendor.remote.remote_id,), queue='metadata')

    return redirect(url_for('vendors.route_restrictions', vendor_id=vendor_id), 302)

@bp_vendors.route('/<int:vendor_id>/namespace/create', methods=['POST', 'GET'])
@login_required
@admin_login_required
def route_namespace_create(vendor_id):
    """ Allows changing a vendor [ADMIN ONLY] """

    # check exists
    vendor = db.session.query(Vendor).filter(Vendor.vendor_id == vendor_id).first()
    if not vendor:
        flash('Failed to get vendor details: No a vendor with that group ID', 'warning')
        return redirect(url_for('vendors.route_list_admin'), 302)
    if 'value' in request.form:
        ns = Namespace(value=request.form['value'], user=g.user)
    elif 'value' in request.args:
        ns = Namespace(value=request.args['value'], user=g.user)
    else:
        return _error_internal('No value')
    if not ns.is_valid:
        flash('Failed to add namespace: Invalid value, expecting something like com.dell', 'warning')
        return redirect(url_for('vendors.route_namespaces', vendor_id=vendor_id))
    vendor.namespaces.append(ns)
    db.session.commit()
    flash('Added namespace', 'info')
    return redirect(url_for('vendors.route_namespaces', vendor_id=vendor_id), 302)

@bp_vendors.route('/<int:vendor_id>/namespace/<int:namespace_id>/delete', methods=['POST'])
@login_required
@admin_login_required
def route_namespace_delete(vendor_id, namespace_id):
    """ Allows changing a vendor [ADMIN ONLY] """

    # check exists
    vendor = db.session.query(Vendor).filter(Vendor.vendor_id == vendor_id).first()
    if not vendor:
        flash('Failed to get vendor details: No a vendor with that group ID', 'warning')
        return redirect(url_for('vendors.route_list_admin'), 302)
    for res in vendor.namespaces:
        if res.namespace_id == namespace_id:
            db.session.delete(res)
            db.session.commit()
            break
    flash('Deleted namespace', 'info')
    return redirect(url_for('vendors.route_namespaces', vendor_id=vendor_id), 302)

@bp_vendors.route('/<int:vendor_id>/modify_by_admin', methods=['GET', 'POST'])
@login_required
@admin_login_required
def route_modify_by_admin(vendor_id):
    """ Change details about the any vendor """

    # only accept form data
    if request.method != 'POST':
        return redirect(url_for('vendors.route_list_admin'))

    # save to database
    vendor = db.session.query(Vendor).filter(Vendor.vendor_id == vendor_id).first()
    if not vendor:
        flash('Failed to modify vendor: No a vendor with that group ID', 'warning')
        return redirect(url_for('vendors.route_list_admin'), 302)
    for key in ['display_name',
                'internal_team',
                'group_id',
                'plugins',
                'quote_text',
                'quote_author',
                'consulting_text',
                'consulting_link',
                'description',
                'oauth_unknown_user',
                'oauth_domain_glob',
                'comments',
                'username_glob',
                'verfmt_id',
                'url',
                'keywords']:
        if key in request.form:
            setattr(vendor, key, request.form[key] if request.form[key] else None)
            # special case so that the embargo name matches
            if key == 'group_id':
                vendor.remote.name = 'embargo-{}'.format(vendor.group_id)
    for key in ['is_embargo_default',
                'do_not_track',
                'visible',
                'visible_on_landing',
                'visible_for_search']:
        if key in request.form:
            setattr(vendor, key, bool(request.form[key] == '1'))
    db.session.commit()
    flash('Updated vendor', 'info')
    return redirect(url_for('vendors.route_show', vendor_id=vendor_id), 302)

@bp_vendors.route('/<int:vendor_id>/upload', methods=['POST'])
@login_required
@admin_login_required
def route_upload(vendor_id):

    # check exists
    vendor = db.session.query(Vendor).filter(Vendor.vendor_id == vendor_id).first()
    if not vendor:
        flash('Failed to modify vendor: No a vendor with that group ID', 'warning')
        return redirect(url_for('vendors.route_list_admin'), 302)

    # not correct parameters
    if not 'file' in request.files:
        return _error_internal('No file')

    # write the pixmap
    buf = request.files['file'].read()
    hmac_dig = _vendor_hash(vendor)
    fn = os.path.join(app.config['UPLOAD_DIR'], 'vendor-{}.png'.format(hmac_dig))
    with open(fn, 'wb') as f:
        f.write(buf)

    vendor.icon = os.path.basename(fn)
    db.session.commit()
    flash('Modified vendor', 'info')

    return redirect(url_for('vendors.route_show', vendor_id=vendor_id), 302)

def _verify_username_vendor_glob(username, username_glob):
    for tmp in username_glob.split(','):
        if fnmatch.fnmatch(username, tmp):
            return True
    return False

@bp_vendors.route('/<int:vendor_id>/user/create', methods=['POST'])
@login_required
def route_user_create(vendor_id):
    """ Add a user to the vendor """

    # check exists
    vendor = db.session.query(Vendor).filter(Vendor.vendor_id == vendor_id).first()
    if not vendor:
        flash('Failed to modify vendor: No a vendor with that group ID', 'warning')
        return redirect(url_for('vendors.route_list'), 302)

    # security check
    if not vendor.check_acl('@manage-users'):
        flash('Permission denied: Unable to modify vendor as non-admin', 'danger')
        return redirect(url_for('vendors.route_show', vendor_id=vendor_id))

    if not 'username' in request.form or not request.form['username']:
        flash('Unable to add user as no username', 'danger')
        return redirect(url_for('vendors.route_show', vendor_id=vendor_id))
    if not 'display_name' in request.form:
        flash('Unable to add user as no display_name', 'danger')
        return redirect(url_for('vendors.route_show', vendor_id=vendor_id))
    username = request.form['username'].lower()
    user = db.session.query(User).filter(User.username == username).first()
    if user:
        flash('Failed to add user: Username already exists', 'warning')
        return redirect(url_for('vendors.route_users', vendor_id=vendor_id), 302)

    # verify email
    if not _email_check(username):
        flash('Failed to add user: Invalid email address', 'warning')
        return redirect(url_for('users.route_list'), 302)

    # verify the username matches the allowed vendor glob
    if not g.user.check_acl('@admin'):
        if not vendor.username_glob:
            flash('Failed to add user: '
                  'Admin has not set the account policy for this vendor',
                  'warning')
            return redirect(url_for('vendors.route_users', vendor_id=vendor_id), 302)
        if not _verify_username_vendor_glob(username, vendor.username_glob):
            flash('Failed to add user: '
                  'Email address does not match account policy %s' % vendor.username_glob,
                  'warning')
            return redirect(url_for('vendors.route_users', vendor_id=vendor_id), 302)

    # add user
    if g.user.vendor.oauth_domain_glob:
        user = User(username=username,
                    display_name=request.form['display_name'],
                    auth_type='oauth',
                    vendor_id=vendor.vendor_id)
    else:
        user = User(username=username,
                    display_name=request.form['display_name'],
                    auth_type='local',
                    otp_secret=_otp_hash(),
                    vendor_id=vendor.vendor_id)
        # this is stored hashed
        password = _generate_password()
        user.password = password
    db.session.add(user)
    db.session.commit()

    # send email
    if user.auth_type == 'local':
        send_email("[LVFS] An account has been created",
                   user.email_address,
                   render_template('email-confirm.txt',
                                   user=user, password=password))

    # done!
    flash('Added user %i' % user.user_id, 'info')
    return redirect(url_for('vendors.route_users', vendor_id=vendor_id), 302)

@bp_vendors.route('/<int:vendor_id>/affiliations')
@login_required
def route_affiliations(vendor_id):
    """ Allows changing vendor affiliations [ADMIN ONLY] """

    # check exists
    vendor = db.session.query(Vendor).filter(Vendor.vendor_id == vendor_id).first()
    if not vendor:
        flash('Failed to get vendor details: No a vendor with that group ID', 'warning')
        return redirect(url_for('vendors.route_list'), 302)

    # security check
    if not vendor.check_acl('@view-affiliations'):
        flash('Permission denied: Unable to view affiliations', 'danger')
        return redirect(url_for('vendors.route_show', vendor_id=vendor_id))

    # ACLs possible for the OEM to grant to the ODM
    possible_actions = {
        '@delete': 'Delete firmware',
        '@promote-stable': 'Promote firmware to stable',
        '@promote-testing': 'Promote firmware to testing',
        '@modify': 'Modify firmware update details',
        '@modify-affiliation': 'Modify firmware affiliation',
        '@nuke': 'Delete firmware permanently',
        '@modify-limit': 'Change download limits for firmware',
        '@undelete': 'Undelete firmware',
        '@view': 'View firmware',
        '@view-analytics': 'View analytics about firmware',
        '@modify-updateinfo': 'Modify the update release notes',
        '@modify-keywords': 'Add and remove firmware keywords',
        '@modify-requirements': 'Modify firmware requirements, e.g. fwupd version',
        '@modify-checksums': 'Add and remove device checksums, e.g. PCR0',
        '@retry': 'Retry a failed test',
        '@waive': 'Waive a failing test',
    }

    # add other vendors
    vendors = []
    for v in db.session.query(Vendor).order_by(Vendor.display_name):
        if v.vendor_id == vendor_id:
            continue
        if not v.is_account_holder:
            continue
        if v.is_affiliate_for(vendor.vendor_id):
            continue
        vendors.append(v)
    return render_template('vendor-affiliations.html',
                           category='vendors',
                           v=vendor,
                           possible_actions=possible_actions,
                           other_vendors=vendors)

@bp_vendors.route('/<int:vendor_id>/affiliation/<int:affiliation_id>/action/create/<action>', methods=['POST'])
@login_required
def route_affiliation_action_create(vendor_id, affiliation_id, action):
    """ add an ACL action to an existing affiliation """

    # security check
    vendor = db.session.query(Vendor).filter(Vendor.vendor_id == vendor_id).first()
    if not vendor:
        flash('Failed to get vendor details: No a vendor with that ID', 'warning')
        return redirect(url_for('main.route_dashboard'))
    if not vendor.check_acl('@modify-affiliation-actions'):
        flash('Permission denied: Unable to modify vendor affiliation', 'danger')
        return redirect(url_for('vendors.route_affiliations', vendor_id=vendor_id))

    # already exists?
    aff = db.session.query(Affiliation).filter(Affiliation.affiliation_id == affiliation_id).first()
    if not aff:
        flash('Failed to add action: No affiliation with that ID', 'warning')
        return redirect(url_for('vendors.route_affiliations', vendor_id=vendor_id))
    if not action.startswith('@'):
        flash('Failed to add action: Expected "@" prefix', 'warning')
        return redirect(url_for('vendors.route_affiliations', vendor_id=vendor_id))
    if aff.get_action(action):
        flash('Failed to add action: Already present', 'warning')
        return redirect(url_for('vendors.route_affiliations', vendor_id=vendor_id))

    # add
    aff.actions.append(AffiliationAction(action=action, user=g.user))
    db.session.commit()
    flash('Added action', 'info')
    return redirect(url_for('vendors.route_affiliations', vendor_id=vendor_id))

@bp_vendors.route('/<int:vendor_id>/affiliation/<int:affiliation_id>/action/remove/<action>', methods=['POST'])
@login_required
def route_affiliation_action_remove(vendor_id, affiliation_id, action):
    """ remove an ACL action to an existing affiliation """

    # security check
    vendor = db.session.query(Vendor).filter(Vendor.vendor_id == vendor_id).first()
    if not vendor:
        flash('Failed to get vendor details: No a vendor with that ID', 'warning')
        return redirect(url_for('main.route_dashboard'))
    if not vendor.check_acl('@modify-affiliation-actions'):
        flash('Permission denied: Unable to modify vendor affiliation', 'danger')
        return redirect(url_for('vendors.route_affiliations', vendor_id=vendor_id))

    # already exists?
    aff = db.session.query(Affiliation).filter(Affiliation.affiliation_id == affiliation_id).first()
    if not aff:
        flash('Failed to remove action: No affiliation with that ID', 'warning')
        return redirect(url_for('vendors.route_affiliations', vendor_id=vendor_id))
    if not aff.get_action(action):
        flash('Failed to remove action: Not present', 'warning')
        return redirect(url_for('vendors.route_affiliations', vendor_id=vendor_id))

    # remove
    for act in aff.actions:
        if act.action == action:
            aff.actions.remove(act)
    db.session.commit()
    flash('Removed action', 'info')
    return redirect(url_for('vendors.route_affiliations', vendor_id=vendor_id))

@bp_vendors.route('/<int:vendor_id>/affiliation/create', methods=['POST'])
@login_required
def route_affiliation_create(vendor_id):
    """ Allows changing a vendor [ADMIN ONLY] """

    # check exists
    vendor = db.session.query(Vendor).filter(Vendor.vendor_id == vendor_id).first()
    if not vendor:
        flash('Failed to add affiliate: No a vendor with that group ID', 'warning')
        return redirect(url_for('vendors.route_affiliations', vendor_id=vendor_id), 302)
    if not 'vendor_id_odm' in request.form:
        return _error_internal('No value')

    # security check
    if not vendor.check_acl('@modify-affiliations'):
        flash('Permission denied: Unable to add vendor affiliation', 'danger')
        return redirect(url_for('vendors.route_show', vendor_id=vendor_id))

    # check if it already exists
    vendor_id_odm = int(request.form['vendor_id_odm'])
    for rel in vendor.affiliations:
        if rel.vendor_id_odm == vendor_id_odm:
            flash('Failed to add affiliate: Already a affiliation with that ODM', 'warning')
            return redirect(url_for('vendors.route_affiliations', vendor_id=vendor_id), 302)

    # add a new ODM -> OEM affiliation
    aff = Affiliation(vendor_id=vendor_id, vendor_id_odm=vendor_id_odm)
    for action in ['@delete',
                   '@modify',
                   '@undelete',
                   '@modify-updateinfo',
                   '@view',
                   '@retry',
                   '@waive']:
        aff.actions.append(AffiliationAction(action=action, user=g.user))
    vendor.affiliations.append(aff)
    db.session.commit()
    flash('Added affiliation {}'.format(aff.affiliation_id), 'info')
    return redirect(url_for('vendors.route_affiliations', vendor_id=vendor_id), 302)

@bp_vendors.route('/<int:vendor_id>/affiliation/<int:affiliation_id>/delete', methods=['POST'])
@login_required
def route_affiliation_delete(vendor_id, affiliation_id):
    """ Allows changing a vendor [ADMIN ONLY] """

    # check exists
    vendor = db.session.query(Vendor).filter(Vendor.vendor_id == vendor_id).first()
    if not vendor:
        flash('Failed to get vendor details: No a vendor with that group ID', 'warning')
        return redirect(url_for('vendors.route_list'), 302)

    # security check
    if not vendor.check_acl('@modify-affiliations'):
        flash('Permission denied: Unable to delete vendor affiliations', 'danger')
        return redirect(url_for('vendors.route_show', vendor_id=vendor_id))

    for res in vendor.affiliations:
        if res.affiliation_id == affiliation_id:
            db.session.delete(res)
            db.session.commit()
            break
    flash('Deleted affiliation', 'info')
    return redirect(url_for('vendors.route_affiliations', vendor_id=vendor_id), 302)

@bp_vendors.route('/<int:vendor_id>/exports')
@login_required
def route_exports(vendor_id):

    # check exists
    vendor = db.session.query(Vendor).filter(Vendor.vendor_id == vendor_id).first()
    if not vendor:
        flash('Failed to get vendor details: No a vendor with that ID', 'warning')
        return redirect(url_for('vendors.route_list'), 302)

    # security check
    if not vendor.check_acl('@view-exports'):
        flash('Permission denied: Unable to view exports', 'danger')
        return redirect(url_for('vendors.route_show', vendor_id=vendor_id))

    # add other vendors
    vendors = []
    for v in db.session.query(Vendor).order_by(Vendor.display_name):
        if v.vendor_id == vendor_id:
            continue
        if not v.is_account_holder:
            continue
        if v.is_affiliate_for(vendor.vendor_id):
            continue
        vendors.append(v)
    return render_template('vendor-exports.html',
                           category='vendors',
                           v=vendor,
                           other_vendors=vendors)

def _convert_export_ids(v):
    if not v.banned_country_codes:
        return []
    return v.banned_country_codes.split(',')

@bp_vendors.route('/<int:vendor_id>/country/create', methods=['POST'])
@login_required
def route_export_create(vendor_id):

    # check exists
    vendor = db.session.query(Vendor).filter(Vendor.vendor_id == vendor_id).first()
    if not vendor:
        flash('Failed to add affiliate: No a vendor with that ID', 'warning')
        return redirect(url_for('vendors.route_exports', vendor_id=vendor_id), 302)
    if not 'export_id' in request.form:
        return _error_internal('No value')

    # security check
    if not vendor.check_acl('@modify-exports'):
        flash('Permission denied: Unable to add vendor country', 'danger')
        return redirect(url_for('vendors.route_show', vendor_id=vendor_id))

    # check if it already exists
    export_id = request.form['export_id']
    export_ids = _convert_export_ids(vendor)
    if export_id in export_ids:
        flash('Failed to add country: Already blocked %s' % export_id, 'warning')
        return redirect(url_for('vendors.route_exports', vendor_id=vendor_id), 302)

    # add a new ODM -> OEM country
    export_ids.append(export_id)
    vendor.banned_country_codes = ','.join(export_ids)
    db.session.commit()
    flash('Added blocked country %s' % export_id, 'info')
    return redirect(url_for('vendors.route_exports', vendor_id=vendor_id), 302)

@bp_vendors.route('/<int:vendor_id>/country/<export_id>/delete', methods=['POST'])
@login_required
def route_export_delete(vendor_id, export_id):

    # check exists
    vendor = db.session.query(Vendor).filter(Vendor.vendor_id == vendor_id).first()
    if not vendor:
        flash('Failed to get vendor details: No a vendor with that ID', 'warning')
        return redirect(url_for('vendors.route_list'), 302)

    # security check
    if not vendor.check_acl('@modify-exports'):
        flash('Permission denied: Unable to delete vendor exports', 'danger')
        return redirect(url_for('vendors.route_show', vendor_id=vendor_id))

    export_ids = _convert_export_ids(vendor)
    if export_id not in export_ids:
        flash('Failed to remove country: Not blocked %s' % export_id, 'warning')
        return redirect(url_for('vendors.route_exports', vendor_id=vendor_id), 302)
    export_ids.remove(export_id)
    vendor.banned_country_codes = ','.join(export_ids)
    db.session.commit()
    flash('Deleted blocked country %s' % export_id, 'info')
    return redirect(url_for('vendors.route_exports', vendor_id=vendor_id), 302)
