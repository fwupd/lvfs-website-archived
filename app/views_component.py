#!/usr/bin/python2
# -*- coding: utf-8 -*-
#
# Copyright (C) 2017-2018 Richard Hughes <richard@hughsie.com>
# Licensed under the GNU General Public License Version 2

from flask import request, url_for, redirect, render_template, flash, g
from flask_login import login_required

from app import app, db

from .models import Requirement, Component, Keyword, Firmware
from .util import _error_internal, _error_permission_denied

def _validate_guid(guid):
    """ Validates if the string is a valid GUID """
    split = guid.split('-')
    if len(split) != 5:
        return False
    if len(split[0]) != 8:
        return False
    if len(split[1]) != 4:
        return False
    if len(split[2]) != 4:
        return False
    if len(split[3]) != 4:
        return False
    if len(split[4]) != 12:
        return False
    return True

@app.route('/lvfs/component/<int:component_id>/all')
def firmware_component_all(component_id):

    # get firmware component
    md = db.session.query(Component).filter(Component.component_id == component_id).first()
    if not md:
        return _error_internal('No component matched!')

    # get all the firmwares that target this component
    fws = []
    for fw in db.session.query(Firmware).\
                    order_by(Firmware.timestamp.desc()).all():
        if not fw.target in ['stable', 'testing']:
            continue
        if not fw.mds:
            continue
        for md_tmp in fw.mds:
            if md_tmp.appstream_id != md.appstream_id:
                continue
            fws.append(fw)
            break
    return render_template('device.html', fws=fws)

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
    flash('Removed requirement %s' % rq.value, 'info')
    return redirect(url_for('.firmware_component_show',
                            component_id=md.component_id,
                            page='requires'))

@app.route('/lvfs/component/requirement/add', methods=['POST'])
@login_required
def firmware_requirement_add():
    """ Adds a requirement to a component """

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
        flash('Cannot add requirement: %s is not a valid GUID' % request.form['value'], 'warning')
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
                flash('Deleted requirement %s' % rq.value, 'info')
                return redirect(url_for('.firmware_component_show',
                                        component_id=md.component_id,
                                        page='requires'))
            rq.compare = request.form['compare']
        db.session.commit()
        flash('Modified requirement %s' % rq.value, 'info')
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
    return redirect(url_for('.firmware_component_show',
                            component_id=md.component_id,
                            page='requires'))

@app.route('/lvfs/component/keyword/<keyword_id>/delete')
@login_required
def firmware_keyword_delete(keyword_id):

    # get firmware component
    kw = db.session.query(Keyword).filter(Keyword.keyword_id == keyword_id).first()
    if not kw:
        return _error_internal('No keyword matched!')

    # get the firmware for the keyword
    md = kw.md
    if not md:
        return _error_internal('No metadata matched!')
    fw = md.fw
    if not fw:
        return _error_internal('No firmware matched!')

    # we can only modify our own firmware, unless admin
    if not g.user.check_for_firmware(fw):
        return _error_permission_denied('Unable to modify other vendor firmware')

    # remove chid
    db.session.delete(kw)
    db.session.commit()

    # log
    flash('Removed keyword %s' % kw.value, 'info')
    return redirect(url_for('.firmware_component_show',
                            component_id=md.component_id,
                            page='keywords'))

@app.route('/lvfs/component/keyword/add', methods=['POST'])
@login_required
def firmware_keyword_add():
    """ Adds one or more keywords to the existing component """

    # check we have data
    for key in ['component_id', 'value']:
        if key not in request.form or not request.form[key]:
            return _error_internal('No %s specified!' % key)

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

    # add keyword
    md.add_keywords_from_string(request.form['value'])
    db.session.commit()
    flash('Added keywords', 'info')
    return redirect(url_for('.firmware_component_show',
                            component_id=md.component_id,
                            page='keywords'))
