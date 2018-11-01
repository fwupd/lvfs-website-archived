#!/usr/bin/python2
# -*- coding: utf-8 -*-
#
# Copyright (C) 2017-2018 Richard Hughes <richard@hughsie.com>
# Licensed under the GNU General Public License Version 2

from flask import request, url_for, redirect, render_template, flash
from flask_login import login_required

from gi.repository import AppStreamGlib
from gi.repository import GLib

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
        if not fw.remote.is_public:
            continue
        if not fw.mds:
            continue
        for md_tmp in fw.mds:
            if md_tmp.appstream_id != md.appstream_id:
                continue
            fws.append(fw)
            break
    return render_template('device.html', fws=fws)

@app.route('/lvfs/component/<int:component_id>/modify', methods=['POST'])
@login_required
def firmware_component_modify(component_id):
    """ Modifies the component properties """

    # find firmware
    md = db.session.query(Component).filter(Component.component_id == component_id).first()
    if not md:
        return _error_internal("No component %s" % component_id)

    # security check
    if not md.check_acl('@modify-updateinfo'):
        return _error_permission_denied('Insufficient permissions to modify firmware')

    # set new metadata values
    page = 'overview'
    if 'screenshot_url' in request.form:
        md.screenshot_url = request.form['screenshot_url']
    if 'screenshot_caption' in request.form:
        md.screenshot_caption = request.form['screenshot_caption']
    if 'urgency' in request.form:
        md.release_urgency = request.form['urgency']
        page = 'update'
    if 'description' in request.form:
        txt = request.form['description']
        if txt:
            if txt.find('<p>') == -1 and txt.find('<li>') == -1:
                txt = AppStreamGlib.markup_import(txt, AppStreamGlib.MarkupConvertFormat.SIMPLE)
            try:
                AppStreamGlib.markup_validate(txt)
            except GLib.Error as e: # pylint: disable=catching-non-exception
                return _error_internal("Failed to parse %s: %s" % (txt, str(e)))
        md.release_description = unicode(txt)

    # modify
    db.session.commit()
    flash('Component updated', 'info')
    return redirect(url_for('.firmware_component_show',
                            component_id=component_id,
                            page=page))

@app.route('/lvfs/component/<int:component_id>')
@app.route('/lvfs/component/<int:component_id>/<page>')
@login_required
def firmware_component_show(component_id, page='overview'):
    """ Show firmware component information """

    # get firmware component
    md = db.session.query(Component).filter(Component.component_id == component_id).first()
    if not md:
        return _error_internal('No component matched!')

    # security check
    fw = md.fw
    if not fw:
        return _error_internal('No firmware matched!')
    if not fw.check_acl('@view'):
        return _error_permission_denied('Unable to view other vendor firmware')

    return render_template('firmware-md-' + page + '.html',
                           md=md, page=page)

@app.route('/lvfs/component/<int:component_id>/requirement/delete/<requirement_id>')
@login_required
def firmware_requirement_delete(component_id, requirement_id):

    # get firmware component
    rq = db.session.query(Requirement).filter(Requirement.requirement_id == requirement_id).first()
    if not rq:
        return _error_internal('No requirement matched!')

    # get the firmware for the requirement
    md = rq.md
    if md.component_id != component_id:
        return _error_internal('Wrong component ID for requirement!')
    if not md:
        return _error_internal('No metadata matched!')

    # security check
    if not md.check_acl('@modify-requirements'):
        return _error_permission_denied('Unable to modify other vendor firmware')

    # remove chid
    db.session.delete(rq)
    db.session.commit()

    # log
    flash('Removed requirement %s' % rq.value, 'info')
    return redirect(url_for('.firmware_component_show',
                            component_id=md.component_id,
                            page='requires'))

@app.route('/lvfs/component/<int:component_id>/requirement/add', methods=['POST'])
@login_required
def firmware_requirement_add(component_id):
    """ Adds a requirement to a component """

    # check we have data
    for key in ['kind', 'value']:
        if key not in request.form or not request.form[key]:
            return _error_internal('No %s specified!' % key)
    if request.form['kind'] not in ['hardware', 'firmware', 'id']:
        return _error_internal('No valid kind specified!')

    # get firmware component
    md = db.session.query(Component).\
            filter(Component.component_id == component_id).first()
    if not md:
        return _error_internal('No component matched!')

    # security check
    if not md.check_acl('@modify-requirements'):
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

@app.route('/lvfs/component/<int:component_id>/keyword/<keyword_id>/delete')
@login_required
def firmware_keyword_delete(component_id, keyword_id):

    # get firmware component
    kw = db.session.query(Keyword).filter(Keyword.keyword_id == keyword_id).first()
    if not kw:
        return _error_internal('No keyword matched!')

    # get the firmware for the keyword
    md = kw.md
    if md.component_id != component_id:
        return _error_internal('Wrong component ID for keyword!')
    if not md:
        return _error_internal('No metadata matched!')

    # security check
    if not md.check_acl('@modify-keywords'):
        return _error_permission_denied('Unable to modify other vendor firmware')

    # remove chid
    db.session.delete(kw)
    db.session.commit()

    # log
    flash('Removed keyword %s' % kw.value, 'info')
    return redirect(url_for('.firmware_component_show',
                            component_id=md.component_id,
                            page='keywords'))

@app.route('/lvfs/component/<int:component_id>/keyword/add', methods=['POST'])
@login_required
def firmware_keyword_add(component_id):
    """ Adds one or more keywords to the existing component """

    # check we have data
    for key in ['value']:
        if key not in request.form or not request.form[key]:
            return _error_internal('No %s specified!' % key)

    # get firmware component
    md = db.session.query(Component).\
            filter(Component.component_id == component_id).first()
    if not md:
        return _error_internal('No component matched!')

    # security check
    if not md.check_acl('@modify-keywords'):
        return _error_permission_denied('Unable to modify other vendor firmware')

    # add keyword
    md.add_keywords_from_string(request.form['value'])
    db.session.commit()
    flash('Added keywords', 'info')
    return redirect(url_for('.firmware_component_show',
                            component_id=md.component_id,
                            page='keywords'))
