#!/usr/bin/python2
# -*- coding: utf-8 -*-
#
# Copyright (C) 2017 Richard Hughes <richard@hughsie.com>
# Licensed under the GNU General Public License Version 2

import os

from glob import fnmatch

from flask import request, flash, url_for, redirect, render_template, g
from flask_login import login_required

from app import app, db

from .emails import send_email
from .util import _error_permission_denied, _error_internal, _email_check
from .models import Vendor, Restriction, User, Remote, Affiliation
from .hash import _password_hash
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

@app.route('/status')
@app.route('/vendorlist') # deprecated
@app.route('/lvfs/vendorlist')
def vendor_list():
    vendors = db.session.query(Vendor).order_by(Vendor.display_name).all()
    vendors.sort(_sort_vendor_func)
    return render_template('vendorlist.html', vendors=vendors)

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
    db.session.delete(vendor.remote)
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


@app.route('/lvfs/vendor/<int:vendor_id>/user/<int:user_id>/disable')
@login_required
def vendor_user_disable(vendor_id, user_id):

    # check exists
    vendor = db.session.query(Vendor).filter(Vendor.vendor_id == vendor_id).first()
    if not vendor:
        flash('Failed to delete user: No vendor with that vendor ID', 'warning')
        return redirect(url_for('.vendor_users', vendor_id=vendor_id))
    user = db.session.query(User).filter(User.user_id == user_id).first()
    if not user:
        flash('Failed to delete user: No user with that user ID', 'warning')
        return redirect(url_for('.vendor_users', vendor_id=vendor_id))

    # security check
    if not vendor.check_acl('@manage-users'):
        return _error_permission_denied('Unable to delete user as non-admin')

    # erase password and set as 'disabled'
    user.password = None
    user.auth_type = None
    db.session.commit()
    return redirect(url_for('.vendor_users', vendor_id=vendor_id))

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
    password = _generate_password()
    user = User(username=request.form['username'],
                display_name=request.form['display_name'],
                auth_type='local',
                password=_password_hash(password),
                vendor_id=vendor.vendor_id)
    db.session.add(user)
    db.session.commit()

    # send email
    send_email("[LVFS] An account has been created",
               user.username,
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
        if v.is_uploading != 'yes':
            continue
        if vendor.get_affiliation_by_odm_id(v.vendor_id):
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
