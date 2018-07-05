#!/usr/bin/python2
# -*- coding: utf-8 -*-
#
# Copyright (C) 2017 Richard Hughes <richard@hughsie.com>
# Licensed under the GNU General Public License Version 2

import datetime

from flask import request, flash, url_for, redirect, render_template, g
from flask_login import login_required

from app import app, db

from .emails import send_email
from .util import _error_internal, _error_permission_denied, _email_check, _generate_password
from .models import User, Vendor, Remote, Firmware, Event, FirmwareEvent
from .hash import _password_hash

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

    # check we got enough data
    if not 'password_new' in request.form:
        return _error_permission_denied('Unable to change user as no data')
    if not 'password_old' in request.form:
        return _error_permission_denied('Unable to change user as no data')
    if not 'display_name' in request.form:
        return _error_permission_denied('Unable to change user as no data')
    old_password_hash = _password_hash(request.form['password_old'])
    user = db.session.query(User).\
            filter(User.user_id == user_id).\
            filter(User.password == old_password_hash).first()
    if not user:
        flash('Failed to modify profile: Incorrect existing password', 'danger')
        return redirect(url_for('.profile'), 302)

    # check password
    password = request.form['password_new']
    if not _password_check(password):
        return redirect(url_for('.profile'), 302)

    # verify name
    display_name = request.form['display_name']
    if len(display_name) < 3:
        flash('Failed to modify profile: Name invalid', 'warning')
        return redirect(url_for('.profile'), 302)

    # save to database
    user.password = _password_hash(password)
    user.display_name = display_name
    user.mtime = datetime.datetime.utcnow()
    db.session.commit()
    flash('Updated profile', 'info')
    return redirect(url_for('.profile'))

@app.route('/lvfs/user/<int:user_id>/reset_by_admin')
@login_required
def user_reset_by_admin(user_id):
    """ Reset the users password """

    # check exists
    user = db.session.query(User).filter(User.user_id == user_id).first()
    if not user:
        return _error_internal('No user with that user_id', 422)

    # security check
    if not user.vendor.check_acl('@manage-users'):
        return _error_permission_denied('Unable to modify user as non-admin')

    # password is stored hashed
    password = _generate_password()
    user.password = _password_hash(password)
    user.mtime = datetime.datetime.utcnow()
    db.session.commit()

    # send email
    send_email("[LVFS] Your password has been reset",
               user.username,
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
        return _error_internal('No user with that user_id', 422)

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

    # set each optional thing in turn
    old_vendor = user.vendor
    for key in ['display_name', 'username', 'username_old', 'auth_type', 'vendor_id']:
        if key in request.form:
            value = request.form[key]
            if value == '':
                value = None
            setattr(user, key, value)

    # unchecked checkbuttons are not included in the form data
    for key in ['is_qa', 'is_analyst', 'is_vendor_manager', 'is_approved_public']:
        setattr(user, key, True if key in request.form else False)

    # password is optional, and hashed
    if 'password' in request.form and request.form['password']:
        user.password = _password_hash(request.form['password'])

    user.mtime = datetime.datetime.utcnow()
    db.session.commit()

    # reparent any uploaded firmware
    is_dirty = False
    reparent = True if 'reparent' in request.form else False
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
                       user.username,
                       render_template('email-moved.txt',
                                       user=user,
                                       old_vendor=old_vendor,
                                       reparent=reparent))
        else:
            send_email("[LVFS] Your account has been updated",
                       user.username,
                       render_template('email-modify.txt', user=user))
        flash('Updated profile and sent a notification email to the user', 'info')
    else:
        flash('Updated profile', 'info')

    return redirect(url_for('.user_admin', user_id=user_id))

@app.route('/lvfs/user/add', methods=['GET', 'POST'])
@login_required
def user_add():
    """ Add a user [ADMIN ONLY] """

    # only accept form data
    if request.method != 'POST':
        return redirect(url_for('.profile'))

    # security check
    if not g.user.check_acl('@admin'):
        return _error_permission_denied('Unable to add user as non-admin')

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
        return _error_internal('Already a user with that username', 422)

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
                password=_password_hash(password),
                display_name=display_name,
                vendor_id=vendor.vendor_id)
    db.session.add(user)
    db.session.commit()
    flash('Added user %i and an email has been sent to the user' % user.user_id, 'info')
    return redirect(url_for('.user_list'), 302)

@app.route('/lvfs/user/<int:user_id>/delete')
@login_required
def user_delete(user_id):
    """ Delete a user """

    # security check
    if not g.user.check_acl('@admin'):
        return _error_permission_denied('Unable to remove user as not admin')

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
def user_list():
    """
    Show a list of all users
    """
    if not g.user.check_acl('@admin'):
        return _error_permission_denied('Unable to show userlist for non-admin user')
    return render_template('userlist.html', users=db.session.query(User).all())

@app.route('/lvfs/user/<int:user_id>/admin')
@login_required
def user_admin(user_id):
    """
    Shows an admin panel for a user
    """

    # check exists
    user = db.session.query(User).filter(User.user_id == user_id).first()
    if not user:
        flash('No user found', 'danger')
        return redirect(url_for('.user_list'), 422)

    # check user is not trying to edit themselves using the admin panel
    if user.user_id == g.user.user_id:
        flash('Cannot self edit using admin panel', 'warning')
        return redirect(url_for('.user_list'))

    # security check
    if not user.vendor.check_acl('@manage-users'):
        return _error_permission_denied('Unable to modify user for non-admin user')

    # get all the vendors with LVFS accounts
    if g.user.check_acl('@admin'):
        vendors = db.session.query(Vendor).\
                    filter(Vendor.is_account_holder == 'yes').\
                    order_by(Vendor.display_name).all()
    else:
        vendors = []
    return render_template('useradmin.html', u=user, possible_vendors=vendors)
