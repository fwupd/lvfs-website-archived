#!/usr/bin/python2
# -*- coding: utf-8 -*-
#
# Copyright (C) 2017 Richard Hughes <richard@hughsie.com>
# Licensed under the GNU General Public License Version 2

from flask import request, flash, url_for, redirect, render_template, g
from flask_login import login_required

from app import app, db

from .util import _event_log, _error_internal, _error_permission_denied
from .db import CursorError

@app.route('/lvfs/group/<group_id>/modify_by_admin', methods=['POST'])
@login_required
def group_modify_by_admin(group_id):
    """ Change details about the any group """

    # security check
    if g.user.group_id != 'admin':
        return _error_permission_denied('Unable to modify group as non-admin')

    # set each thing in turn
    for key in ['vendor_ids']:
        # unchecked checkbuttons are not included in the form data
        if key in request.form:
            tmp = request.form[key]
        else:
            tmp = '0'
        try:
            # don't set the optional password
            db.groups.set_property(group_id, key, tmp)
        except CursorError as e:
            return _error_internal(str(e))
    _event_log('Changed group %s properties' % group_id)
    flash('Updated group', 'info')
    return redirect(url_for('.group_admin', group_id=group_id))

@app.route('/lvfs/group/add', methods=['GET', 'POST'])
@login_required
def group_add():
    """ Add a group [ADMIN ONLY] """

    # only accept form data
    if request.method != 'POST':
        return redirect(url_for('.group_list'))

    # security check
    if g.user.group_id != 'admin':
        return _error_permission_denied('Unable to add group as non-admin')

    if not 'group_id' in request.form:
        return _error_permission_denied('Unable to add group as no data')
    try:
        group = db.groups.get_item(request.form['group_id'])
    except CursorError as e:
        return _error_internal(str(e))
    if group:
        return _error_internal('Already a entry with that group', 422)
    db.groups.add(request.form['group_id'])

    _event_log("Created group %s" % request.form['group_id'])
    flash('Added group', 'info')
    return redirect(url_for('.group_list'), 302)

@app.route('/lvfs/group/<group_id>/delete')
@login_required
def group_delete(group_id):
    """ Delete a user """

    # security check
    if g.user.group_id != 'admin':
        return _error_permission_denied('Unable to remove user as not admin')

    # check whether exists in database
    try:
        group = db.groups.get_item(group_id)
    except CursorError as e:
        return _error_internal(str(e))
    if not group:
        flash("No entry with group_id %s" % group_id, 'warning')
        return redirect(url_for('.group_list'), 422)
    try:
        db.groups.remove(group_id)
    except CursorError as e:
        return _error_internal(str(e))
    _event_log("Deleted group %s" % group_id)
    flash('Deleted group', 'info')
    return redirect(url_for('.group_list'), 302)

@app.route('/lvfs/group/<group_id>/admin')
@login_required
def group_admin(group_id):
    """
    Shows an admin panel for a group
    """
    if g.user.group_id != 'admin':
        return _error_permission_denied('Unable to modify group for non-admin user')
    users_filtered = []
    try:
        group = db.groups.get_item(group_id)
        users = db.users.get_all()
        for user in users:
            if user.group_id != group_id:
                continue
            users_filtered.append(user)
    except CursorError as e:
        return _error_internal(str(e))
    return render_template('groupadmin.html', q=group, users=users_filtered)

@app.route('/lvfs/grouplist')
@login_required
def group_list():
    """
    Show a list of all groups
    """
    if g.user.group_id != 'admin':
        return _error_permission_denied('Unable to show grouplist for non-admin user')
    try:
        groups = db.groups.get_all()
    except CursorError as e:
        return _error_internal(str(e))
    return render_template('grouplist.html', groups=groups)
