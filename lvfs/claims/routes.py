#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2020 Richard Hughes <richard@hughsie.com>
#
# SPDX-License-Identifier: GPL-2.0+

from flask import Blueprint, request, url_for, redirect, flash, render_template
from flask_login import login_required

from lvfs import db

from lvfs.models import Claim
from lvfs.util import _error_internal
from lvfs.util import admin_login_required

bp_claims = Blueprint('claims', __name__, template_folder='templates')

@bp_claims.route('/')
@login_required
@admin_login_required
def route_list():

    # only show claims with the correct group_id
    claims = db.session.query(Claim).order_by(Claim.kind.asc()).all()
    return render_template('claim-list.html',
                           category='admin',
                           claims=claims)

@bp_claims.route('/create', methods=['POST'])
@login_required
@admin_login_required
def route_create():

    # ensure has enough data
    if 'kind' not in request.form:
        return _error_internal('No form data found!')
    kind = request.form['kind']
    if not kind or not kind.islower() or kind.find(' ') != -1:
        flash('Failed to add claim: Value needs to be a lower case word', 'warning')
        return redirect(url_for('claims.route_list'))

    # already exists
    if db.session.query(Claim).filter(Claim.kind == kind).first():
        flash('Failed to add claim: The claim already exists', 'info')
        return redirect(url_for('claims.route_list'))

    # add claim
    claim = Claim(kind=kind, summary=request.form.get('summary'))
    db.session.add(claim)
    db.session.commit()
    flash('Added claim', 'info')
    return redirect(url_for('claims.route_show', claim_id=claim.claim_id))

@bp_claims.route('/<int:claim_id>/delete', methods=['POST'])
@login_required
@admin_login_required
def route_delete(claim_id):

    # get claim
    claim = db.session.query(Claim).\
            filter(Claim.claim_id == claim_id).first()
    if not claim:
        flash('No claim found', 'info')
        return redirect(url_for('claims.route_list'))

    # delete
    db.session.delete(claim)
    db.session.commit()
    flash('Deleted claim', 'info')
    return redirect(url_for('claims.route_list'))

@bp_claims.route('/<int:claim_id>/modify', methods=['POST'])
@login_required
@admin_login_required
def route_modify(claim_id):

    # find claim
    claim = db.session.query(Claim).\
                filter(Claim.claim_id == claim_id).first()
    if not claim:
        flash('No claim found', 'info')
        return redirect(url_for('claims.route_list'))

    # modify claim
    for key in ['kind', 'icon', 'summary', 'url']:
        if key in request.form:
            setattr(claim, key, request.form[key])
    db.session.commit()

    # success
    flash('Modified claim', 'info')
    return redirect(url_for('claims.route_show', claim_id=claim_id))

@bp_claims.route('/<int:claim_id>/details')
@login_required
@admin_login_required
def route_show(claim_id):

    # find claim
    claim = db.session.query(Claim).\
            filter(Claim.claim_id == claim_id).first()
    if not claim:
        flash('No claim found', 'info')
        return redirect(url_for('claims.route_list'))

    # show details
    return render_template('claim-details.html',
                           claim=claim)
