#!/usr/bin/python2
# -*- coding: utf-8 -*-
#
# Copyright (C) 2017 Richard Hughes <richard@hughsie.com>
# Licensed under the GNU General Public License Version 2

from flask import request, flash, url_for, redirect, render_template, g
from flask_login import login_required

from app import app, db

from .util import _event_log, _error_internal, _error_permission_denied
from .models import UserCapability

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

def _email_check(value):
    """ Do a quick and dirty check on the email address """
    if len(value) < 5 or value.find('@') == -1 or value.find('.') == -1:
        return False
    return True

@app.route('/lvfs/user/<username>/modify', methods=['GET', 'POST'])
@login_required
def user_modify(username):
    """ Change details about the current user """

    # only accept form data
    if request.method != 'POST':
        return redirect(url_for('.profile'))

    # security check
    if g.user.username != username:
        return _error_permission_denied('Unable to modify a different user')
    if g.user.is_locked:
        return _error_permission_denied('Unable to change user as account locked')

    # check we got enough data
    if not 'password_new' in request.form:
        return _error_permission_denied('Unable to change user as no data')
    if not 'password_old' in request.form:
        return _error_permission_denied('Unable to change user as no data')
    if not 'name' in request.form:
        return _error_permission_denied('Unable to change user as no data')
    if not 'email' in request.form:
        return _error_permission_denied('Unable to change user as no data')
    if not db.users.verify(g.user.username, request.form['password_old']):
        flash('Incorrect existing password', 'danger')
        return redirect(url_for('.profile'), 302)

    # check password
    password = request.form['password_new']
    if not _password_check(password):
        return redirect(url_for('.profile'), 302)

    # check email
    email = request.form['email']
    if not _email_check(email):
        flash('Invalid email address', 'warning')
        return redirect(url_for('.profile'))

    # verify name
    name = request.form['name']
    if len(name) < 3:
        flash('Name invalid', 'warning')
        return redirect(url_for('.profile'), 302)
    db.users.update(g.user.username, password, name, email)
    #session['password'] = _password_hash(password)
    _event_log('Changed password')
    flash('Updated profile', 'info')
    return redirect(url_for('.profile'))

@app.route('/lvfs/user/<username>/modify_by_admin', methods=['POST'])
@login_required
def user_modify_by_admin(username):
    """ Change details about the any user """

    # security check
    if not g.user.check_capability(UserCapability.Admin):
        return _error_permission_denied('Unable to modify user as non-admin')

    # set each thing in turn
    for key in ['group_id',
                'display_name',
                'email',
                'password',
                'is_enabled',
                'is_qa',
                'is_analyst',
                'is_locked']:
        # unchecked checkbuttons are not included in the form data
        if key in request.form:
            tmp = request.form[key]
        else:
            tmp = '0'
        # don't set the optional password
        if key == 'password' and len(tmp) == 0:
            continue
        db.users.set_property(username, key, tmp)
    _event_log('Changed user %s properties' % username)
    flash('Updated profile', 'info')
    return redirect(url_for('.user_admin', username=username))

@app.route('/lvfs/user/add', methods=['GET', 'POST'])
@login_required
def user_add():
    """ Add a user [ADMIN ONLY] """

    # only accept form data
    if request.method != 'POST':
        return redirect(url_for('.profile'))

    # security check
    if not g.user.check_capability(UserCapability.Admin):
        return _error_permission_denied('Unable to add user as non-admin')

    if not 'password_new' in request.form:
        return _error_permission_denied('Unable to add user as no password_new')
    if not 'username_new' in request.form:
        return _error_permission_denied('Unable to add user as no username_new')
    if not 'group_id' in request.form:
        return _error_permission_denied('Unable to add user as no group_id')
    if not 'name' in request.form:
        return _error_permission_denied('Unable to add user as no name')
    if not 'email' in request.form:
        return _error_permission_denied('Unable to add user as no email')
    if db.users.is_enabled(request.form['username_new']):
        return _error_internal('Already a entry with that username', 422)

    # verify password
    password = request.form['password_new']
    if not _password_check(password):
        return redirect(url_for('.user_list'), 422)

    # verify email
    email = request.form['email']
    if not _email_check(email):
        flash('Invalid email address', 'warning')
        return redirect(url_for('.user_list'), 422)

    # verify group_id
    group_id = request.form['group_id']
    if len(group_id) < 3:
        flash('QA group invalid', 'warning')
        return redirect(url_for('.user_list'), 422)

    # verify name
    name = request.form['name']
    if len(name) < 3:
        flash('Name invalid', 'warning')
        return redirect(url_for('.user_list'), 422)

    # verify username
    username_new = request.form['username_new']
    if len(username_new) < 3:
        flash('Username invalid', 'warning')
        return redirect(url_for('.user_list'), 422)
    db.users.add(username_new, password, name, email, group_id)
    if not db.groups.get_item(group_id):
        db.groups.add(group_id)

    _event_log("Created user %s" % username_new)
    flash('Added user', 'info')
    return redirect(url_for('.user_list'), 302)

@app.route('/lvfs/user/<username>/delete')
@login_required
def user_delete(username):
    """ Delete a user """

    # security check
    if not g.user.check_capability(UserCapability.Admin):
        return _error_permission_denied('Unable to remove user as not admin')

    # check whether exists in database
    if not db.users.is_enabled(username):
        flash("No entry with username %s" % username, 'danger')
        return redirect(url_for('.user_list'), 422)
    db.users.remove(username)
    _event_log("Deleted user %s" % username)
    flash('Deleted user', 'info')
    return redirect(url_for('.user_list'), 302)

@app.route('/lvfs/userlist')
@login_required
def user_list():
    """
    Show a list of all users
    """
    if not g.user.check_capability(UserCapability.Admin):
        return _error_permission_denied('Unable to show userlist for non-admin user')
    return render_template('userlist.html', users=db.users.get_all())

@app.route('/lvfs/user/<username>/admin')
@login_required
def user_admin(username):
    """
    Shows an admin panel for a user
    """
    if not g.user.check_capability(UserCapability.Admin):
        return _error_permission_denied('Unable to modify user for non-admin user')
    return render_template('useradmin.html', u=db.users.get_item(username))
