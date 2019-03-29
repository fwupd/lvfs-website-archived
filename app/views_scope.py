#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2019 Richard Hughes <richard@hughsie.com>
# Licensed under the GNU General Public License Version 2

from flask import request, url_for, redirect, flash, g, render_template
from flask_login import login_required

from app import app, db

from .models import Scope
from .util import _error_internal, _error_permission_denied

@app.route('/lvfs/scope/all')
@login_required
def scope_all():

    # security check
    if not g.user.check_acl('@view-scopes'):
        return _error_permission_denied('Unable to view scopes')

    # only show scopes with the correct group_id
    scopes = db.session.query(Scope).order_by(Scope.scope_id.asc()).all()
    return render_template('scope-list.html', scopes=scopes)

@app.route('/lvfs/scope/add', methods=['POST'])
@login_required
def scope_add():

    # security check
    if not Scope('').check_acl('@create'):
        return _error_permission_denied('Unable to add scope')

    # ensure has enough data
    if 'value' not in request.form:
        return _error_internal('No form data found!')
    value = request.form['value']
    if not value or not value.islower() or value.find(' ') != -1:
        flash('Failed to add scope: Value needs to be a lower case word', 'warning')
        return redirect(url_for('.scope_all'))

    # already exists
    if db.session.query(Scope).filter(Scope.value == value).first():
        flash('Failed to add scope: The scope already exists', 'info')
        return redirect(url_for('.scope_all'))

    # add scope
    sco = Scope(value=request.form['value'])
    db.session.add(sco)
    db.session.commit()
    flash('Added scope', 'info')
    return redirect(url_for('.scope_details', scope_id=sco.scope_id))

@app.route('/lvfs/scope/<int:scope_id>/delete')
@login_required
def scope_delete(scope_id):

    # get scope
    sco = db.session.query(Scope).\
            filter(Scope.scope_id == scope_id).first()
    if not sco:
        flash('No scope found', 'info')
        return redirect(url_for('.scope_all'))

    # security check
    if not sco.check_acl('@modify'):
        return _error_permission_denied('Unable to delete scope')

    # delete
    db.session.delete(sco)
    db.session.commit()
    flash('Deleted scope', 'info')
    return redirect(url_for('.scope_all'))

@app.route('/lvfs/scope/<int:scope_id>/modify', methods=['POST'])
@login_required
def scope_modify(scope_id):

    # find scope
    sco = db.session.query(Scope).\
                filter(Scope.scope_id == scope_id).first()
    if not sco:
        flash('No scope found', 'info')
        return redirect(url_for('.scope_all'))

    # security check
    if not sco.check_acl('@modify'):
        return _error_permission_denied('Unable to modify scope')

    # modify scope
    for key in ['name']:
        if key in request.form:
            setattr(sco, key, request.form[key])
    db.session.commit()

    # success
    flash('Modified scope', 'info')
    return redirect(url_for('.scope_details', scope_id=scope_id))

@app.route('/lvfs/scope/<int:scope_id>/details')
@login_required
def scope_details(scope_id):

    # find scope
    sco = db.session.query(Scope).\
            filter(Scope.scope_id == scope_id).first()
    if not sco:
        flash('No scope found', 'info')
        return redirect(url_for('.scope_all'))

    # security check
    if not sco.check_acl('@view'):
        return _error_permission_denied('Unable to view scope details')

    # show details
    return render_template('scope-details.html', sco=sco)
