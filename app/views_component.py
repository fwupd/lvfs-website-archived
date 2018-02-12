#!/usr/bin/python2
# -*- coding: utf-8 -*-
#
# Copyright (C) 2017-2018 Richard Hughes <richard@hughsie.com>
# Licensed under the GNU General Public License Version 2

from flask import request, url_for, redirect, render_template, flash, g
from flask_login import login_required

from app import app, db

from .models import Requirement, Component
from .util import _event_log, _error_internal, _error_permission_denied, _validate_guid

@app.route('/lvfs/component/<int:component_id>')
@app.route('/lvfs/component/<int:component_id>/<page>')
@login_required
def firmware_component_show(component_id, page='overview'):
    """ Show firmware component information """

    # get firmware component
    md = db.session.query(Component).filter(Component.component_id == component_id).first()
    if not md:
        return _error_internal('No component matched!')

    # we can only view our own firmware, unless admin
    fw = md.fw
    if not fw:
        return _error_internal('No firmware matched!')
    if not g.user.check_for_firmware(fw, readonly=True):
        return _error_permission_denied('Unable to view other vendor firmware')

    return render_template('firmware-md-' + page + '.html',
                           md=md, fw=fw)

@app.route('/lvfs/component/requirement/delete/<requirement_id>')
@login_required
def firmware_requirement_delete(requirement_id):

    # get firmware component
    rq = db.session.query(Requirement).filter(Requirement.requirement_id == requirement_id).first()
    if not rq:
        return _error_internal('No requirement matched!')

    # get the firmware for the requirement
    md = rq.md
    if not md:
        return _error_internal('No metadata matched!')
    fw = md.fw
    if not fw:
        return _error_internal('No firmware matched!')

    # we can only modify our own firmware, unless admin
    if not g.user.check_for_firmware(fw):
        return _error_permission_denied('Unable to modify other vendor firmware')

    # remove chid
    db.session.delete(rq)
    db.session.commit()

    # log
    flash('Removed requirement', 'info')
    _event_log('Removed requirement %s on %s' % (rq.value, fw.firmware_id))
    return redirect(url_for('.firmware_component_show',
                            component_id=md.component_id,
                            page='requires'))

@app.route('/lvfs/component/requirement/add', methods=['POST'])
@login_required
def firmware_requirement_add():
    """ Modifies the update urgency and release notes for the update """

    # check we have data
    for key in ['component_id', 'kind', 'value']:
        if key not in request.form or not request.form[key]:
            return _error_internal('No %s specified!' % key)
    if request.form['kind'] not in ['hardware', 'firmware', 'id']:
        return _error_internal('No valid kind specified!')

    # get firmware component
    md = db.session.query(Component).\
            filter(Component.component_id == request.form['component_id']).first()
    if not md:
        return _error_internal('No component matched!')
    fw = md.fw
    if not fw:
        return _error_internal('No firmware matched!')

    # we can only modify our own firmware, unless admin
    if not g.user.check_for_firmware(fw):
        return _error_permission_denied('Unable to modify other vendor firmware')

    # validate CHID is a valid GUID
    if request.form['kind'] == 'hardware' and not _validate_guid(request.form['value']):
        flash('%s was not a valid GUID' % request.form['value'], 'danger')
        return redirect(url_for('.firmware_component_show',
                                component_id=md.component_id,
                                page='requires'))

    # check it's not already been added
    rq = md.find_req(request.form['kind'], request.form['value'])
    if rq:
        if 'version' in request.form:
            rq.version = request.form['version']
        if 'compare' in request.form:
            if request.form['compare'] == 'any':
                db.session.delete(rq)
                db.session.commit()
                flash('Deleted requirement', 'info')
                return redirect(url_for('.firmware_component_show',
                                        component_id=md.component_id,
                                        page='requires'))
            rq.compare = request.form['compare']
        db.session.commit()
        flash('Modified requirement', 'info')
        return redirect(url_for('.firmware_component_show',
                                component_id=md.component_id,
                                page='requires'))

    # add requirement
    rq = Requirement(md.component_id,
                     request.form['kind'],
                     request.form['value'],
                     request.form['compare'] if 'compare' in request.form else None,
                     request.form['version'] if 'version' in request.form else None,
                    )
    md.requirements.append(rq)
    db.session.commit()
    flash('Added requirement', 'info')
    _event_log('Added requirement %s on %s' % (request.form['value'], fw.firmware_id))
    return redirect(url_for('.firmware_component_show',
                            component_id=md.component_id,
                            page='requires'))
