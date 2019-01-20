#!/usr/bin/python2
# -*- coding: utf-8 -*-
#
# Copyright (C) 2017 Richard Hughes <richard@hughsie.com>
# Licensed under the GNU General Public License Version 2
#
# pylint: disable=too-few-public-methods

import os

from glob import fnmatch

from flask import request, flash, url_for, redirect, render_template, g
from flask_login import login_required
from sqlalchemy.orm import joinedload

from app import app, db

from .emails import send_email
from .util import _error_permission_denied, _error_internal, _email_check
from .models import Vendor, Restriction, User, Remote, Affiliation
from .util import _generate_password

# sort by awesomeness
def _sort_vendor_func(a, b):
    a_val = a.get_sort_key()
    b_val = b.get_sort_key()
    if a_val > b_val:
        return -1
    if a_val < b_val:
        return 1
    return 0

def _count_vendor_fws_public(vendor, remote_name):
    dedupe_csum = {}
    for fw in vendor.fws:
        if fw.remote.name == remote_name:
            dedupe_csum[fw.checksum_upload] = True
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

class VendorStat(object):
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
    vendors = sorted(display_names.items(),
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

@app.route('/lvfs/vendorlist/<page>')
def vendor_list_analytics(page):
    vendors = db.session.query(Vendor).\
                order_by(Vendor.display_name).\
                options(joinedload('fws')).all()
    if page == 'publicfw':
        labels, data_stable, data_testing = _get_vendorlist_stats(vendors, _count_vendor_fws_public)
        return render_template('vendorlist-analytics.html', vendors=vendors,
                               title='Total number of public firmware files',
                               page=page, labels=labels,
                               data_stable=data_stable,
                               data_testing=data_testing)
    if page == 'downloads':
        labels, data_stable, data_testing = _get_vendorlist_stats(vendors, _count_vendor_fws_downloads)
        return render_template('vendorlist-analytics.html', vendors=vendors,
                               title='Percentage of firmware downloads',
                               page=page, labels=labels,
                               data_stable=_abs_to_pc(data_stable, data_testing),
                               data_testing=_abs_to_pc(data_testing, data_stable))
    if page == 'devices':
        labels, data_stable, data_testing = _get_vendorlist_stats(vendors, _count_vendor_fws_devices)
        return render_template('vendorlist-analytics.html', vendors=vendors,
                               title='Total number of supported devices',
                               page=page, labels=labels,
                               data_stable=data_stable,
                               data_testing=data_testing)
    return _error_internal('Vendorlist kind invalid')

@app.route('/status')
@app.route('/vendorlist') # deprecated
@app.route('/lvfs/vendorlist')
def vendor_list():
    vendors = db.session.query(Vendor).order_by(Vendor.display_name).all()
    vendors.sort(_sort_vendor_func)
    return render_template('vendorlist.html', vendors=vendors, page='overview')

@app.route('/lvfs/vendor/add', methods=['GET', 'POST'])
@login_required
def vendor_add():
    """ Add a vendor [ADMIN ONLY] """

    # only accept form data
    if request.method != 'POST':
        return redirect(url_for('.vendor_list'))

    # security check
    if not g.user.check_acl('@admin'):
        return _error_permission_denied('Unable to add vendor as non-admin')

    if not 'group_id' in request.form:
        return _error_permission_denied('Unable to add vendor as no data')
    if db.session.query(Vendor).filter(Vendor.group_id == request.form['group_id']).first():
        flash('Failed to add vendor: Group ID already exists', 'warning')
        return redirect(url_for('.vendor_list'), 302)
    r = Remote(name='embargo-%s' % request.form['group_id'])
    db.session.add(r)
    db.session.commit()
    v = Vendor(request.form['group_id'], remote_id=r.remote_id)
    db.session.add(v)
    db.session.commit()
    flash('Added vendor %s' % request.form['group_id'], 'info')
    return redirect(url_for('.vendor_details', vendor_id=v.vendor_id), 302)

@app.route('/lvfs/vendor/<int:vendor_id>/delete')
@login_required
def vendor_delete(vendor_id):
    """ Removes a vendor [ADMIN ONLY] """

    # security check
    if not g.user.check_acl('@admin'):
        return _error_permission_denied('Unable to remove vendor as non-admin')
    vendor = db.session.query(Vendor).filter(Vendor.vendor_id == vendor_id).first()
    if not vendor:
        flash('Failed to delete vendor: No a vendor with that group ID', 'warning')
        return redirect(url_for('.vendor_list'), 302)
    db.session.delete(vendor)
    db.session.commit()
    flash('Removed vendor', 'info')
    return redirect(url_for('.vendor_list'), 302)

@app.route('/lvfs/vendor/<int:vendor_id>')
@app.route('/lvfs/vendor/<int:vendor_id>/details')
@login_required
def vendor_details(vendor_id):
    """ Allows changing a vendor [ADMIN ONLY] """

    # security check
    if not g.user.check_acl('@admin'):
        return _error_permission_denied('Unable to edit vendor as non-admin')
    vendor = db.session.query(Vendor).filter(Vendor.vendor_id == vendor_id).first()
    if not vendor:
        flash('Failed to get vendor details: No a vendor with that group ID', 'warning')
        return redirect(url_for('.vendor_list'), 302)
    return render_template('vendor-details.html', v=vendor)

@app.route('/lvfs/vendor/<int:vendor_id>/restrictions')
@login_required
def vendor_restrictions(vendor_id):
    """ Allows changing a vendor [ADMIN ONLY] """

    # security check
    if not g.user.check_acl('@admin'):
        return _error_permission_denied('Unable to edit vendor as non-admin')
    vendor = db.session.query(Vendor).filter(Vendor.vendor_id == vendor_id).first()
    if not vendor:
        flash('Failed to get vendor details: No a vendor with that group ID', 'warning')
        return redirect(url_for('.vendor_list'), 302)
    return render_template('vendor-restrictions.html', v=vendor)

@app.route('/lvfs/vendor/<int:vendor_id>/event')
@login_required
def vendor_event(vendor_id):
    """ Allows changing a vendor """

    # security check
    vendor = db.session.query(Vendor).filter(Vendor.vendor_id == vendor_id).first()
    if not vendor:
        flash('Failed to get vendor details: No a vendor with that group ID', 'warning')
        return redirect(url_for('.vendor_list'), 302)
    if not vendor.check_acl('@manage-users'):
        return _error_permission_denied('Unable to view event log')
    return render_template('vendor-event.html', v=vendor, page='event')

@app.route('/lvfs/vendor/<int:vendor_id>/users')
@login_required
def vendor_users(vendor_id):
    """ Allows changing a vendor [ADMIN ONLY] """

    # check exists
    vendor = db.session.query(Vendor).filter(Vendor.vendor_id == vendor_id).first()
    if not vendor:
        flash('Failed to get vendor details: No a vendor with that group ID', 'warning')
        return redirect(url_for('.vendor_list'), 302)

    # security check
    if not vendor.check_acl('@manage-users'):
        return _error_permission_denied('Unable to edit vendor as non-admin')
    return render_template('vendor-users.html', v=vendor)

@app.route('/lvfs/vendor/<int:vendor_id>/oauth')
@login_required
def vendor_oauth(vendor_id):
    """ Allows changing a vendor [ADMIN ONLY] """

    # check exists
    vendor = db.session.query(Vendor).filter(Vendor.vendor_id == vendor_id).first()
    if not vendor:
        flash('Failed to get vendor details: No a vendor with that group ID', 'warning')
        return redirect(url_for('.vendor_list'), 302)

    # security check
    if not vendor.check_acl('@modify-oauth'):
        return _error_permission_denied('Unable to edit vendor as non-admin')
    return render_template('vendor-oauth.html', v=vendor)

@app.route('/lvfs/vendor/<int:vendor_id>/restriction/add', methods=['POST'])
@login_required
def vendor_restriction_add(vendor_id):
    """ Allows changing a vendor [ADMIN ONLY] """

    # security check
    if not g.user.check_acl('@admin'):
        return _error_permission_denied('Unable to edit vendor as non-admin')

    # check exists
    vendor = db.session.query(Vendor).filter(Vendor.vendor_id == vendor_id).first()
    if not vendor:
        flash('Failed to get vendor details: No a vendor with that group ID', 'warning')
        return redirect(url_for('.vendor_list'), 302)
    if not 'value' in request.form:
        return _error_internal('No value')
    vendor.restrictions.append(Restriction(request.form['value']))
    db.session.commit()
    flash('Added restriction', 'info')
    return redirect(url_for('.vendor_restrictions', vendor_id=vendor_id), 302)

@app.route('/lvfs/vendor/<int:vendor_id>/restriction/<int:restriction_id>/delete')
@login_required
def vendor_restriction_delete(vendor_id, restriction_id):
    """ Allows changing a vendor [ADMIN ONLY] """

    # security check
    if not g.user.check_acl('@admin'):
        return _error_permission_denied('Unable to edit vendor as non-admin')

    # check exists
    vendor = db.session.query(Vendor).filter(Vendor.vendor_id == vendor_id).first()
    if not vendor:
        flash('Failed to get vendor details: No a vendor with that group ID', 'warning')
        return redirect(url_for('.vendor_list'), 302)
    for res in vendor.restrictions:
        if res.restriction_id == restriction_id:
            db.session.delete(res)
            db.session.commit()
            break
    flash('Deleted restriction', 'info')
    return redirect(url_for('.vendor_restrictions', vendor_id=vendor_id), 302)

@app.route('/lvfs/vendor/<int:vendor_id>/modify_by_admin', methods=['GET', 'POST'])
@login_required
def vendor_modify_by_admin(vendor_id):
    """ Change details about the any vendor """

    # only accept form data
    if request.method != 'POST':
        return redirect(url_for('.vendor_list'))

    # security check
    if not g.user.check_acl('@admin'):
        return _error_permission_denied('Unable to modify vendor as non-admin')

    # save to database
    vendor = db.session.query(Vendor).filter(Vendor.vendor_id == vendor_id).first()
    if not vendor:
        flash('Failed to modify vendor: No a vendor with that group ID', 'warning')
        return redirect(url_for('.vendor_list'), 302)
    for key in ['display_name',
                'plugins',
                'description',
                'is_fwupd_supported',
                'is_account_holder',
                'is_uploading',
                'oauth_unknown_user',
                'oauth_domain_glob',
                'comments',
                'username_glob',
                'version_format',
                'url',
                'keywords']:
        if key in request.form:
            setattr(vendor, key, request.form[key])
    for key in ['is_embargo_default',
                'visible',
                'visible_for_search']:
        if key in request.form:
            setattr(vendor, key, True if request.form[key] == '1' else False)
    db.session.commit()
    flash('Updated vendor', 'info')
    return redirect(url_for('.vendor_list'))

@app.route('/lvfs/vendor/<int:vendor_id>/upload', methods=['POST'])
@login_required
def vendor_upload(vendor_id):

    # security check
    if not g.user.check_acl('@admin'):
        return _error_permission_denied('Unable to modify vendor as non-admin')

    # check exists
    vendor = db.session.query(Vendor).filter(Vendor.vendor_id == vendor_id).first()
    if not vendor:
        flash('Failed to modify vendor: No a vendor with that group ID', 'warning')
        return redirect(url_for('.vendor_list'), 302)

    # not correct parameters
    if not 'file' in request.files:
        return _error_internal('No file')

    # write the pixmap
    buf = request.files['file'].read()
    fn = os.path.join(app.config['UPLOAD_DIR'], 'vendor-%s.png' % vendor_id)
    open(fn, 'wb').write(buf)

    vendor.icon = os.path.basename(fn)
    db.session.commit()
    flash('Modified vendor', 'info')

    return redirect(url_for('.vendor_details', vendor_id=vendor_id), 302)

def _verify_username_vendor_glob(username, username_glob):
    for tmp in username_glob.split(','):
        if fnmatch.fnmatch(username, tmp):
            return True
    return False

@app.route('/lvfs/vendor/<int:vendor_id>/user/add', methods=['POST'])
@login_required
def vendor_user_add(vendor_id):
    """ Add a user to the vendor """

    # check exists
    vendor = db.session.query(Vendor).filter(Vendor.vendor_id == vendor_id).first()
    if not vendor:
        flash('Failed to modify vendor: No a vendor with that group ID', 'warning')
        return redirect(url_for('.vendor_list'), 302)

    # security check
    if not vendor.check_acl('@manage-users'):
        return _error_permission_denied('Unable to modify vendor as non-admin')

    if not 'username' in request.form or not request.form['username']:
        return _error_permission_denied('Unable to add user as no username')
    if not 'display_name' in request.form:
        return _error_permission_denied('Unable to add user as no display_name')
    user = db.session.query(User).filter(User.username == request.form['username']).first()
    if user:
        flash('Failed to add user: Username already exists', 'warning')
        return redirect(url_for('.vendor_users', vendor_id=vendor_id), 302)

    # verify email
    if not _email_check(request.form['username']):
        flash('Failed to add user: Invalid email address', 'warning')
        return redirect(url_for('.user_list'), 302)

    # verify the username matches the allowed vendor glob
    if not g.user.is_admin:
        if not vendor.username_glob:
            flash('Failed to add user: '
                  'Admin has not set the account policy for this vendor',
                  'warning')
        if not _verify_username_vendor_glob(request.form['username'].lower(),
                                            vendor.username_glob):
            flash('Failed to add user: '
                  'Email address does not match account policy %s' % vendor.username_glob,
                  'warning')
            return redirect(url_for('.vendor_users', vendor_id=vendor_id), 302)

    # add user
    if g.user.vendor.oauth_domain_glob:
        user = User(username=request.form['username'],
                    display_name=request.form['display_name'],
                    auth_type='oauth',
                    vendor_id=vendor.vendor_id)
    else:
        user = User(username=request.form['username'],
                    display_name=request.form['display_name'],
                    auth_type='local',
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
    return redirect(url_for('.vendor_users', vendor_id=vendor_id), 302)

@app.route('/lvfs/vendor/<int:vendor_id>/affiliations')
@login_required
def vendor_affiliations(vendor_id):
    """ Allows changing vendor affiliations [ADMIN ONLY] """

    # check exists
    vendor = db.session.query(Vendor).filter(Vendor.vendor_id == vendor_id).first()
    if not vendor:
        flash('Failed to get vendor details: No a vendor with that group ID', 'warning')
        return redirect(url_for('.vendor_list'), 302)

    # security check
    if not vendor.check_acl('@view-affiliations'):
        return _error_permission_denied('Unable to view affiliations')

    # add other vendors
    vendors = []
    for v in db.session.query(Vendor).order_by(Vendor.display_name).all():
        if v.vendor_id == vendor_id:
            continue
        if v.is_account_holder != 'yes':
            continue
        if v.is_affiliate_for(vendor.vendor_id):
            continue
        vendors.append(v)
    return render_template('vendor-affiliations.html', v=vendor, other_vendors=vendors)

@app.route('/lvfs/vendor/<int:vendor_id>/affiliation/add', methods=['POST'])
@login_required
def vendor_affiliation_add(vendor_id):
    """ Allows changing a vendor [ADMIN ONLY] """

    # check exists
    vendor = db.session.query(Vendor).filter(Vendor.vendor_id == vendor_id).first()
    if not vendor:
        flash('Failed to add affiliate: No a vendor with that group ID', 'warning')
        return redirect(url_for('.vendor_affiliations', vendor_id=vendor_id), 302)
    if not 'vendor_id_odm' in request.form:
        return _error_internal('No value')

    # security check
    if not vendor.check_acl('@modify-affiliations'):
        return _error_permission_denied('Unable to add vendor affiliation')

    # check if it already exists
    vendor_id_odm = int(request.form['vendor_id_odm'])
    for rel in vendor.affiliations:
        if rel.vendor_id_odm == vendor_id_odm:
            flash('Failed to add affiliate: Already a affiliation with that ODM', 'warning')
            return redirect(url_for('.vendor_affiliations', vendor_id=vendor_id), 302)

    # add a new ODM -> OEM affiliation
    vendor.affiliations.append(Affiliation(vendor_id, vendor_id_odm))
    db.session.commit()
    flash('Added affiliation', 'info')
    return redirect(url_for('.vendor_affiliations', vendor_id=vendor_id), 302)

@app.route('/lvfs/vendor/<int:vendor_id>/affiliation/<int:affiliation_id>/delete')
@login_required
def vendor_affiliation_delete(vendor_id, affiliation_id):
    """ Allows changing a vendor [ADMIN ONLY] """

    # check exists
    vendor = db.session.query(Vendor).filter(Vendor.vendor_id == vendor_id).first()
    if not vendor:
        flash('Failed to get vendor details: No a vendor with that group ID', 'warning')
        return redirect(url_for('.vendor_list'), 302)

    # security check
    if not vendor.check_acl('@modify-affiliations'):
        return _error_permission_denied('Unable to delete vendor affiliations')

    for res in vendor.affiliations:
        if res.affiliation_id == affiliation_id:
            db.session.delete(res)
            db.session.commit()
            break
    flash('Deleted affiliation', 'info')
    return redirect(url_for('.vendor_affiliations', vendor_id=vendor_id), 302)
