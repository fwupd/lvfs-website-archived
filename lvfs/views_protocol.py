#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2018 Richard Hughes <richard@hughsie.com>
#
# SPDX-License-Identifier: GPL-2.0+

from flask import request, url_for, redirect, flash, render_template
from flask_login import login_required

from lvfs import app, db

from .models import Protocol
from .util import _error_internal
from .util import admin_login_required

@app.route('/lvfs/protocols')
@login_required
@admin_login_required
def protocol_all():

    # only show protocols with the correct group_id
    protocols = db.session.query(Protocol).order_by(Protocol.protocol_id.asc()).all()
    return render_template('protocol-list.html',
                           category='admin',
                           protocols=protocols)

@app.route('/lvfs/protocol/add', methods=['POST'])
@login_required
@admin_login_required
def protocol_add():

    # ensure has enough data
    if 'value' not in request.form:
        return _error_internal('No form data found!')
    value = request.form['value']
    if not value or not value.islower() or value.find(' ') != -1:
        flash('Failed to add protocol: Value needs to be a lower case word', 'warning')
        return redirect(url_for('.protocol_all'))

    # already exists
    if db.session.query(Protocol).filter(Protocol.value == value).first():
        flash('Failed to add protocol: The protocol already exists', 'info')
        return redirect(url_for('.protocol_all'))

    # add protocol
    protocol = Protocol(value=request.form['value'])
    db.session.add(protocol)
    db.session.commit()
    flash('Added protocol', 'info')
    return redirect(url_for('.protocol_details', protocol_id=protocol.protocol_id))

@app.route('/lvfs/protocol/<int:protocol_id>/delete')
@login_required
@admin_login_required
def protocol_delete(protocol_id):

    # get protocol
    protocol = db.session.query(Protocol).\
            filter(Protocol.protocol_id == protocol_id).first()
    if not protocol:
        flash('No protocol found', 'info')
        return redirect(url_for('.protocol_all'))

    # delete
    db.session.delete(protocol)
    db.session.commit()
    flash('Deleted protocol', 'info')
    return redirect(url_for('.protocol_all'))

@app.route('/lvfs/protocol/<int:protocol_id>/modify', methods=['POST'])
@login_required
@admin_login_required
def protocol_modify(protocol_id):

    # find protocol
    protocol = db.session.query(Protocol).\
                filter(Protocol.protocol_id == protocol_id).first()
    if not protocol:
        flash('No protocol found', 'info')
        return redirect(url_for('.protocol_all'))

    # modify protocol
    protocol.is_signed = bool('is_signed' in request.form)
    protocol.is_public = bool('is_public' in request.form)
    protocol.can_verify = bool('can_verify' in request.form)
    protocol.has_header = bool('has_header' in request.form)
    for key in ['name']:
        if key in request.form:
            setattr(protocol, key, request.form[key])
    db.session.commit()

    # success
    flash('Modified protocol', 'info')
    return redirect(url_for('.protocol_details', protocol_id=protocol_id))

@app.route('/lvfs/protocol/<int:protocol_id>/details')
@login_required
@admin_login_required
def protocol_details(protocol_id):

    # find protocol
    protocol = db.session.query(Protocol).\
            filter(Protocol.protocol_id == protocol_id).first()
    if not protocol:
        flash('No protocol found', 'info')
        return redirect(url_for('.protocol_all'))

    # show details
    return render_template('protocol-details.html', protocol=protocol)
