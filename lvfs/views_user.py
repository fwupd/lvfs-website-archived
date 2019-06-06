#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2017 Richard Hughes <richard@hughsie.com>
#
# SPDX-License-Identifier: GPL-2.0+

import datetime

from io import BytesIO
import pyqrcode

from flask import request, flash, url_for, redirect, render_template, g
from flask_login import login_required

from lvfs import app, db

from .emails import send_email
from .util import admin_login_required
from .util import _error_internal, _error_permission_denied, _email_check, _generate_password
from .util import _pkcs7_certificate_info
from .models import User, Vendor, Remote, Firmware, Event, FirmwareEvent, Certificate

def _password_check(value):
    """ Check the password for suitability """
    success = True
    if len(value) < 8:
        success = False
        flash('The password is too short, the minimum is 8 characters', 'warning')
    if len(value) > 40:
        success = False
        flash('The password is too long, the maximum is 40 characters', 'warning')
    if value.lower() == value:
        success = False
        flash('The password requires at least one uppercase character', 'warning')
    if value.isalnum():
        success = False
        flash('The password requires at least one non-alphanumeric character', 'warning')
    return success

@app.route('/lvfs/user/<int:user_id>/modify', methods=['GET', 'POST'])
@login_required
def user_modify(user_id):
    """ Change details about the current user """

    # only accept form data
    if request.method != 'POST':
        return redirect(url_for('.profile'))

    # security check
    if g.user.user_id != user_id:
        return _error_permission_denied('Unable to modify a different user')
    if g.user.auth_type == 'local+locked':
        return _error_permission_denied('Unable to change user as account locked')
    if g.user.auth_type == 'oauth':
        return _error_permission_denied('Unable to change OAuth-only user')
    user = db.session.query(User).filter(User.user_id == user_id).first()

    # verify name
    if 'display_name' in request.form:
        display_name = request.form['display_name']
        if len(display_name) < 3:
            flash('Failed to modify profile: Name invalid', 'warning')
            return redirect(url_for('.profile'), 302)
        user.display_name = display_name

    # get the new human_user_id if specified
    if 'human_user' in request.form and request.form['human_user']:
        username = request.form['human_user']
        human_user = db.session.query(User).\
                            filter(User.username == username).first()
        if not human_user:
            flash('Failed to modify profile: Human user %s not found' % username, 'warning')
            return redirect(url_for('.profile'), 302)
        user.human_user_id = human_user.user_id

    # unchecked checkbuttons are not included in the form data
    for key in ['notify_demote_failures']:
        setattr(user, key, bool(key in request.form))

    # save to database
    user.mtime = datetime.datetime.utcnow()
    db.session.commit()
    flash('Updated profile', 'info')
    return redirect(url_for('.profile'))

@app.route('/lvfs/user/<int:user_id>/deactivate')
@login_required
def user_deactivate(user_id):

    # security check
    if g.user.user_id != user_id:
        return _error_permission_denied('Unable to modify a different user')
    if not g.user.check_acl('@manage-password'):
        return _error_permission_denied('Unable to deactivate')
    user = db.session.query(User).filter(User.user_id == user_id).one()
    user.auth_type = 'disabled'
    user.mtime = datetime.datetime.utcnow()
    db.session.commit()
    return redirect(url_for('.logout'))

@app.route('/lvfs/user/<int:user_id>/password', methods=['GET', 'POST'])
@login_required
def user_password(user_id):
    """ Change details about the current user """

    # only accept form data
    if request.method != 'POST':
        return redirect(url_for('.profile'))

    # security check
    if g.user.user_id != user_id:
        return _error_permission_denied('Unable to modify a different user')
    if not g.user.check_acl('@manage-password'):
        return _error_permission_denied('Unable to modify password')

    # check we got enough data
    if not 'password_old' in request.form:
        return _error_permission_denied('Unable to change user as no data')
    if not 'password_new' in request.form:
        return _error_permission_denied('Unable to change user as no data')
    user = db.session.query(User).filter(User.user_id == user_id).one()
    if not user.verify_password(request.form['password_old']):
        flash('Failed to modify profile: Incorrect existing password', 'danger')
        return redirect(url_for('.profile'), 302)

    # check the user typed it correctly
    password = request.form['password_new']
    if 'password_confirm' in request.form:
        if request.form['password_confirm'] != password:
            flash('Failed to modify profile: New passwords did not match', 'warning')
            return redirect(url_for('.profile'), 302)

    # check password
    if not _password_check(password):
        return redirect(url_for('.profile'), 302)

    # password_ts is only updated if it's different
    user.password = password

    # unchecked checkbuttons are not included in the form data
    for key in ['is_otp_enabled']:
        setattr(user, key, bool(key in request.form))

    # user has to have tested OTP before it can be enabled
    if user.is_otp_enabled and not user.is_otp_working:
        flash('Failed to modify profile: OTP has not been tested', 'warning')
        return redirect(url_for('.profile'), 302)

    # save to database
    user.mtime = datetime.datetime.utcnow()
    db.session.commit()
    flash('Updated profile', 'info')
    return redirect(url_for('.profile'))

@app.route('/lvfs/user/<int:user_id>/auth', methods=['GET', 'POST'])
@login_required
def user_auth(user_id):
    """ Change details about the current user """

    # only accept form data
    if request.method != 'POST':
        return redirect(url_for('.profile'))

    # security check
    if g.user.user_id != user_id:
        return _error_permission_denied('Unable to modify a different user')
    if not g.user.check_acl('@manage-password'):
        return _error_permission_denied('Unable to modify password')

    # unchecked checkbuttons are not included in the form data
    user = db.session.query(User).filter(User.user_id == user_id).one()
    for key in ['is_otp_enabled']:
        setattr(user, key, bool(key in request.form))

    # user has to have tested OTP before it can be enabled
    if user.is_otp_enabled and not user.is_otp_working:
        flash('Failed to modify profile: OTP has not been tested', 'warning')
        return redirect(url_for('.profile'), 302)

    # save to database
    user.mtime = datetime.datetime.utcnow()
    db.session.commit()
    flash('Updated profile', 'info')
    return redirect(url_for('.profile'))

@app.route('/lvfs/user/qrcode')
@login_required
def user_qrcode():

    # security check
    if not g.user.check_acl('@view-profile'):
        return _error_permission_denied('Unable to view profile as account locked')

    # render qrcode for FreeTOTP
    url = pyqrcode.create(g.user.get_totp_uri())
    stream = BytesIO()
    url.svg(stream, scale=5)
    return stream.getvalue(), 200, {
        'Content-Type': 'image/svg+xml',
        'Cache-Control': 'no-cache, no-store, must-revalidate',
        'Pragma': 'no-cache',
        'Expires': '0'}

@app.route('/lvfs/user/otp_test', methods=['POST'])
@login_required
def user_otp_test():

    # security check
    if not g.user.check_acl('@view-profile'):
        return _error_permission_denied('Unable to view profile as account locked')

    # check was sent
    if not 'otp' in request.form or not request.form['otp']:
        flash('2FA OTP not set, cannot test', 'warning')
        return redirect(url_for('.profile'))

    # do dummy test
    if not g.user.verify_totp(request.form['otp']):
        flash('Incorrect 2FA OTP, please check time and date', 'warning')
        return redirect(url_for('.profile'))

    # success
    g.user.is_otp_working = True
    db.session.commit()
    flash('Correct 2FA OTP, it worked!', 'success')
    return redirect(url_for('.profile'))

@app.route('/lvfs/user/<int:user_id>/reset_by_admin')
@login_required
def user_reset_by_admin(user_id):
    """ Reset the users password """

    # check exists
    user = db.session.query(User).filter(User.user_id == user_id).first()
    if not user:
        flash('No user matched!', 'danger')
        return redirect(url_for('.dashboard'), 422)

    # security check
    if not user.vendor.check_acl('@manage-users'):
        return _error_permission_denied('Unable to modify user as non-admin')

    # password is stored hashed
    password = _generate_password()
    user.password = password
    user.mtime = datetime.datetime.utcnow()
    user.password_ts = None
    db.session.commit()

    # send email
    send_email("[LVFS] Your password has been reset",
               user.email_address,
               render_template('email-modify-password.txt',
                               user=user, password=password))

    flash('Password has been reset and an email has been sent to the user', 'info')
    return redirect(url_for('.user_admin', user_id=user_id))

@app.route('/lvfs/user/<int:user_id>/modify_by_admin', methods=['POST'])
@login_required
def user_modify_by_admin(user_id):
    """ Change details about the any user """

    # check exists
    user = db.session.query(User).filter(User.user_id == user_id).first()
    if not user:
        flash('No user matched!', 'danger')
        return redirect(url_for('.dashboard'), 422)

    # security check
    if not user.vendor.check_acl('@manage-users'):
        return _error_permission_denied('Unable to modify user as non-admin')
    if not g.user.check_acl('@admin') and 'vendor_id' in request.form:
        return _error_permission_denied('Unable to modify group for user as non-admin')

    # user is being promoted, so check the manager already has this attribute
    if not user.is_vendor_manager and 'is_vendor_manager' in request.form:
        if not g.user.check_acl('@add-attribute-manager'):
            return _error_permission_denied('Unable to promote user to manager')
    if not user.is_analyst and 'is_analyst' in request.form:
        if not g.user.check_acl('@add-attribute-analyst'):
            return _error_permission_denied('Unable to promote user to analyst')
    if not user.is_qa and 'is_qa' in request.form:
        if not g.user.check_acl('@add-attribute-qa'):
            return _error_permission_denied('Unable to promote user to QA')
    if not user.is_approved_public and 'is_approved_public' in request.form:
        if not g.user.check_acl('@add-attribute-qa'):
            return _error_permission_denied('Unable to promote user to QA')
    if not user.is_robot and 'is_robot' in request.form:
        if not g.user.check_acl('@add-attribute-robot'):
            return _error_permission_denied('Unable to mark user as robot')
    if not user.is_admin and 'is_admin' in request.form:
        if not g.user.check_acl('@add-attribute-admin'):
            return _error_permission_denied('Unable to mark user as admin')

    # set each optional thing in turn
    old_vendor = user.vendor
    for key in ['display_name', 'username', 'auth_type', 'vendor_id', 'auth_warning']:
        if key in request.form:
            value = request.form[key]
            if value == '':
                value = None
            setattr(user, key, value)

    # get the new human_user_id if specified
    if 'human_user' in request.form:
        username = request.form['human_user']
        if username:
            human_user = db.session.query(User).\
                                filter(User.username == username).first()
            if not human_user:
                flash('Failed to modify profile: Human user %s not found' % username, 'warning')
                return redirect(url_for('.profile'), 302)
            user.human_user_id = human_user.user_id
        else:
            user.human_user_id = None

    # unchecked checkbuttons are not included in the form data
    for key in ['is_qa', 'is_analyst', 'is_vendor_manager',
                'is_approved_public', 'is_robot', 'is_admin',
                'is_otp_enabled', 'notify_demote_failures']:
        setattr(user, key, bool(key in request.form))

    # password is optional, and hashed
    if 'password' in request.form and request.form['password']:
        user.password = request.form['password']

    # was disabled?
    if user.auth_type == 'disabled':
        if not user.dtime:
            user.dtime = datetime.datetime.utcnow()
    else:
        user.dtime = None

    user.mtime = datetime.datetime.utcnow()
    db.session.commit()

    # reparent any uploaded firmware
    is_dirty = False
    reparent = bool('reparent' in request.form)
    if old_vendor.vendor_id != user.vendor_id and reparent:
        for fw in db.session.query(Firmware).\
                    filter(Firmware.user_id == user.user_id).all():
            fw.vendor_id = user.vendor_id
            if fw.remote.name.startswith('embargo'):
                is_dirty = True
            fw.remote_id = user.vendor.remote.remote_id
        for ev in db.session.query(FirmwareEvent).\
                    filter(FirmwareEvent.user_id == user.user_id).all():
            ev.remote_id = user.vendor.remote.remote_id

    # fix event log
    if old_vendor.vendor_id != user.vendor_id:
        for ev in db.session.query(Event).\
                    filter(Event.user_id == user.user_id).all():
            ev.vendor_id = user.vendor_id

    # mark both remotes as dirty
    if is_dirty:
        user.vendor.remote.is_dirty = True
        old_vendor.remote.is_dirty = True
    db.session.commit()

    # send email
    if 'send_email' in request.form:
        if old_vendor.vendor_id != user.vendor_id:
            send_email("[LVFS] Your account has been moved",
                       user.email_address,
                       render_template('email-moved.txt',
                                       user=user,
                                       old_vendor=old_vendor,
                                       reparent=reparent))
        else:
            if user.auth_type == 'disabled':
                send_email("[LVFS] Your account has been disabled",
                           user.email_address,
                           render_template('email-disabled.txt', user=user))
            else:
                send_email("[LVFS] Your account has been updated",
                           user.email_address,
                           render_template('email-modify.txt', user=user))
        flash('Updated profile and sent a notification email to the user', 'info')
    else:
        flash('Updated profile', 'info')

    return redirect(url_for('.user_admin', user_id=user_id))

@app.route('/lvfs/user/recover/<secret>')
def user_recover_with_secret(secret):

    # check we have the right token
    user = db.session.query(User).filter(User.password_recovery == secret).first()
    if not user:
        flash('No user with that recovery password', 'danger')
        return redirect(url_for('.index'), 302)

    # user has since been disabled
    if user.auth_type == 'disabled':
        flash('User has been disabled since the recovery email was sent', 'danger')
        return redirect(url_for('.index'), 302)

    # user waited too long
    if datetime.datetime.utcnow() > user.password_recovery_ts + datetime.timedelta(hours=24):
        flash('More than 24 hours elapsed since the recovery email was sent', 'warning')
        return redirect(url_for('.index'), 302)

    # password is stored hashed
    password = _generate_password()
    user.password = password
    user.password_ts = None
    user.password_recovery = None
    user.password_recovery_ts = None
    user.mtime = datetime.datetime.utcnow()
    db.session.commit()

    # send email
    send_email("[LVFS] Your password has been reset",
               user.email_address,
               render_template('email-recover-password.txt',
                               user=user, password=password))
    flash('Your password has been reset and an email has been sent with the new details', 'info')
    return redirect(url_for('.index'), 302)

@app.route('/lvfs/user/recover', methods=['GET', 'POST'])
def user_recover():
    """
    Shows an account recovery panel for a user
    """
    if request.method != 'POST':
        return render_template('user-recover.html')
    if not 'username' in request.form:
        return _error_permission_denied('Unable to recover user as no username')

    # check exists
    username = request.form['username']
    user = db.session.query(User).filter(User.username == username).first()
    if not user:
        flash('Unable to recover password as no username %s found' % username, 'warning')
        return redirect(url_for('.index'), 302)

    # set the recovery password
    try:
        user.generate_password_recovery()
        db.session.commit()
    except RuntimeError as e:
        flash('Unable to recover password for %s: %s' % (username, str(e)), 'warning')
        return redirect(url_for('.index'), 302)

    # send email
    send_email("[LVFS] Your login details",
               user.email_address,
               render_template('email-recover.txt', user=user))
    flash('An email has been sent with a recovery link', 'info')
    return redirect(url_for('.index'), 302)

@app.route('/lvfs/user/certificate/remove/<int:certificate_id>')
@login_required
def user_certificate_remove(certificate_id):

    # check cert exists
    crt = db.session.query(Certificate).filter(Certificate.certificate_id == certificate_id).first()
    if not crt:
        flash('No certificate matched!', 'danger')
        return redirect(url_for('.dashboard'), 422)

    # security check
    if not crt.check_acl('@delete'):
        return _error_permission_denied('Unable to delete certificate')

    # delete
    db.session.delete(crt)
    db.session.commit()
    flash('Deleted certificate', 'info')
    return redirect(url_for('.profile'))

@app.route('/lvfs/user/certificate/add', methods=['GET', 'POST'])
@login_required
def user_certificate_add():

    # only accept form data
    if request.method != 'POST':
        return redirect(url_for('.profile'), code=302)

    # security check
    if not g.user.check_acl('@view-profile'):
        return _error_permission_denied('Unable to add certificate as account locked')

    # check was sent
    if not 'file' in request.files:
        return _error_internal('No file')
    fileitem = request.files['file']
    if not fileitem:
        return _error_internal('No file object')
    try:
        text = fileitem.read().decode('utf8')
    except UnicodeDecodeError as e:
        flash('Invalid data received: %s' % str(e), 'warning')
        return redirect(url_for('.profile'), code=302)
    if not text:
        flash('No data recieved', 'warning')
        return redirect(url_for('.profile'), code=302)
    if text.find('BEGIN CERTIFICATE') == -1:
        flash('Certificate invalid, expected BEGIN CERTIFICATE', 'warning')
        return redirect(url_for('.profile'), code=302)

    # get serial for blob
    try:
        info = _pkcs7_certificate_info(text)
    except IOError as e:
        flash('Certificate invalid, cannot parse: %s' % str(e), 'warning')
        return redirect(url_for('.profile'), code=302)
    if 'serial' not in info:
        flash('Certificate invalid, cannot parse serial', 'warning')
        return redirect(url_for('.profile'), code=302)

    # check cert exists
    crt = db.session.query(Certificate).filter(Certificate.serial == info['serial']).first()
    if crt:
        flash('Certificate already in use', 'warning')
        return redirect(url_for('.profile'), code=302)

    # success
    crt = Certificate(g.user.user_id, info['serial'], text)
    db.session.add(crt)
    db.session.commit()
    flash('Added client certificate with serial %s' % info['serial'], 'success')
    return redirect(url_for('.profile'), code=302)

@app.route('/lvfs/user/add', methods=['GET', 'POST'])
@login_required
@admin_login_required
def user_add():
    """ Add a user [ADMIN ONLY] """

    # only accept form data
    if request.method != 'POST':
        return redirect(url_for('.profile'))

    if not 'username' in request.form:
        return _error_permission_denied('Unable to add user as no username')
    if not 'password_new' in request.form:
        return _error_permission_denied('Unable to add user as no password_new')
    if not 'group_id' in request.form:
        return _error_permission_denied('Unable to add user as no group_id')
    if not 'display_name' in request.form:
        return _error_permission_denied('Unable to add user as no display_name')
    user = db.session.query(User).filter(User.username == request.form['username']).first()
    if user:
        flash('Already a user with that username!', 'danger')
        return redirect(url_for('.dashboard'), 422)

    # verify password
    password = request.form['password_new']
    if not _password_check(password):
        return redirect(url_for('.user_list'), 302)

    # verify email
    username = request.form['username']
    if not _email_check(username):
        flash('Failed to add user: Invalid email address', 'warning')
        return redirect(url_for('.user_list'), 302)

    # verify group_id
    group_id = request.form['group_id']
    if len(group_id) < 3:
        flash('Failed to add user: QA group invalid', 'warning')
        return redirect(url_for('.user_list'), 302)

    # verify name
    display_name = request.form['display_name']
    if len(display_name) < 3:
        flash('Failed to add user: Name invalid', 'warning')
        return redirect(url_for('.user_list'), 302)

    vendor = db.session.query(Vendor).filter(Vendor.group_id == group_id).first()
    if not vendor:
        remote = Remote(name='embargo-%s' % group_id)
        db.session.add(remote)
        db.session.commit()
        vendor = Vendor(group_id, remote_id=remote.remote_id)
        db.session.add(vendor)
        db.session.commit()
    user = User(username=username,
                auth_type='local',
                display_name=display_name,
                vendor_id=vendor.vendor_id)
    user.password = password
    db.session.add(user)
    db.session.commit()
    flash('Added user %i and an email has been sent to the user' % user.user_id, 'info')
    return redirect(url_for('.user_list'), 302)

@app.route('/lvfs/user/<int:user_id>/delete')
@login_required
@admin_login_required
def user_delete(user_id):
    """ Delete a user """

    # check whether exists in database
    user = db.session.query(User).filter(User.user_id == user_id).first()
    if not user:
        flash('Failed to delete user: No user found', 'danger')
        return redirect(url_for('.user_list'), 422)
    db.session.delete(user)
    db.session.commit()
    flash('Deleted user', 'info')
    return redirect(url_for('.user_list'), 302)

@app.route('/lvfs/userlist')
@login_required
@admin_login_required
def user_list():
    """
    Show a list of all users
    """
    return render_template('userlist.html',
                           category='admin',
                           users=db.session.query(User).all())

@app.route('/lvfs/user/<int:user_id>')
@app.route('/lvfs/user/<int:user_id>/<page>')
@login_required
def user_admin(user_id, page='admin'):
    """
    Shows an admin panel for a user
    """

    # check exists
    user = db.session.query(User).filter(User.user_id == user_id).first()
    if not user:
        flash('No user found', 'danger')
        return redirect(url_for('.user_list'), 422)

    # security check
    if not user.vendor.check_acl('@manage-users'):
        return _error_permission_denied('Unable to modify user for non-admin user')

    # get all the vendors with LVFS accounts
    vendors = []
    if g.user.check_acl('@admin'):
        for v in db.session.query(Vendor).order_by(Vendor.display_name).all():
            if v.is_account_holder:
                vendors.append(v)
    return render_template('user-%s.html' % page, page=page, u=user, possible_vendors=vendors)
