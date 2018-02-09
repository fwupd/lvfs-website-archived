#!/usr/bin/python2
# -*- coding: utf-8 -*-
#
# Copyright (C) 2017 Richard Hughes <richard@hughsie.com>
# Licensed under the GNU General Public License Version 2

from flask import request, flash, url_for, redirect, render_template, g
from flask_login import login_required

from app import app, db

from .util import _event_log, _error_internal, _error_permission_denied
from .models import UserCapability, User, Group

@app.route('/lvfs/group/<group_id>/modify_by_admin', methods=['POST'])
@login_required
def group_modify_by_admin(group_id):
    """ Change details about the any group """

    # security check
    if not g.user.check_capability(UserCapability.Admin):
        return _error_permission_denied('Unable to modify group as non-admin')

    # get group
    group = db.session.query(Group).filter(Group.group_id == group_id).first()
    if not group:
        return _error_internal('No group with that ID', 422)

    # this is handled unsplit :/
    if 'vendor_ids' in request.form:
        group.vendor_ids = request.form['vendor_ids'].split(',')
    db.session.commit()
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
    if not g.user.check_capability(UserCapability.Admin):
        return _error_permission_denied('Unable to add group as non-admin')

    if not 'group_id' in request.form:
        return _error_permission_denied('Unable to add group as no data')
    if db.session.query(Group).filter(Group.group_id == request.form['group_id']).first():
        return _error_internal('Already a entry with that group', 422)
    db.session.add(Group(request.form['group_id']))
    db.session.commit()

    _event_log("Created group %s" % request.form['group_id'])
    flash('Added group', 'info')
    return redirect(url_for('.group_list'), 302)

@app.route('/lvfs/group/<group_id>/delete')
@login_required
def group_delete(group_id):
    """ Delete a user """

    # security check
    if not g.user.check_capability(UserCapability.Admin):
        return _error_permission_denied('Unable to remove user as not admin')

    # check whether exists in database
    group = db.session.query(Group).filter(Group.group_id == group_id).first()
    if not group:
        flash("No entry with group_id %s" % group_id, 'warning')
        return redirect(url_for('.group_list'), 302)
    db.session.delete(group)
    db.session.commit()
    _event_log("Deleted group %s" % group_id)
    flash('Deleted group', 'info')
    return redirect(url_for('.group_list'), 302)

@app.route('/lvfs/group/<group_id>/admin')
@login_required
def group_admin(group_id):
    """
    Shows an admin panel for a group
    """
    if not g.user.check_capability(UserCapability.Admin):
        return _error_permission_denied('Unable to modify group for non-admin user')
    users = []
    group = db.session.query(Group).filter(Group.group_id == group_id).first()
    for user in db.session.query(User).all():
        if user.group_id != group_id:
            continue
        users.append(user)
    return render_template('groupadmin.html', q=group, users=users)

@app.route('/lvfs/grouplist')
@login_required
def group_list():
    """
    Show a list of all groups
    """
    if not g.user.check_capability(UserCapability.Admin):
        return _error_permission_denied('Unable to show grouplist for non-admin user')
    return render_template('grouplist.html', groups=db.session.query(Group).all())
