#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2017-2018 Richard Hughes <richard@hughsie.com>
# Licensed under the GNU General Public License Version 2

from flask import request, url_for, redirect, render_template, flash
from flask_login import login_required

from sqlalchemy import func

from app import app, db, ploader

from .models import Requirement, Component, Keyword, Checksum, Scope
from .models import Protocol, Report, ReportAttribute
from .util import _error_internal, _error_permission_denied
from .hash import _is_sha1, _is_sha256

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

def _sanitize_markdown_text(txt):
    txt = txt.replace('\r', '')
    new_lines = []
    for line in txt.split('\n'):
        new_lines.append(line.strip())
    return '\n'.join(new_lines)

@app.route('/lvfs/component/problems')
@login_required
def firmware_component_problems():
    """
    Show all components with problems
    """
    mds = []
    for md in db.session.query(Component).\
                order_by(Component.release_timestamp.desc()).all():
        if not md.problems:
            continue
        if not md.check_acl('@modify-updateinfo'):
            continue
        if md.fw.is_deleted:
            continue
        mds.append(md)
    return render_template('component-problems.html', mds=mds)

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
    if 'protocol_id' in request.form:
        md.protocol_id = request.form['protocol_id']
    if 'scope_id' in request.form:
        md.scope_id = request.form['scope_id']
    if 'screenshot_caption' in request.form:
        md.screenshot_caption = _sanitize_markdown_text(request.form['screenshot_caption'])
    if 'install_duration' in request.form:
        try:
            md.install_duration = int(request.form['install_duration'])
        except ValueError as _:
            md.install_duration = 0
        page = 'install_duration'
    if 'urgency' in request.form:
        md.release_urgency = request.form['urgency']
        page = 'update'
    if 'description' in request.form:
        md.release_description = _sanitize_markdown_text(request.form['description'])
        page = 'update'
    if 'details_url' in request.form:
        md.details_url = request.form['details_url']
        page = 'update'
    if 'source_url' in request.form:
        md.source_url = request.form['source_url']
        page = 'update'

    # ensure the test has been added for the new firmware type
    ploader.ensure_test_for_fw(md.fw)

    # modify
    md.fw.mark_dirty()
    db.session.commit()
    flash('Component updated', 'info')
    return redirect(url_for('.firmware_component_show',
                            component_id=component_id,
                            page=page))

@app.route('/lvfs/component/<int:component_id>/checksums')
@login_required
def firmware_component_checksums(component_id):
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
        return _error_permission_denied('Unable to view component')

    # find reports witch device checkums that match this firmware
    checksum_counts = db.session.query(func.count(ReportAttribute.value),
                                       ReportAttribute.value).\
                                       join(Report).\
                                       filter(Report.firmware_id == fw.firmware_id).\
                                       filter(ReportAttribute.key == 'ChecksumDevice').\
                                       group_by(ReportAttribute.value).all()
    device_checksums = []
    for csum in md.device_checksums:
        device_checksums.append(csum.value)
    return render_template('component-checksums.html',
                           md=md, page='checksums',
                           device_checksums=device_checksums,
                           checksum_counts=checksum_counts)

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

    # firmware requirements are too complicated to show on the simplified fiew
    if page == 'requires' and md.has_complex_requirements:
        page = 'requires-advanced'

    protocols = db.session.query(Protocol).order_by(Protocol.protocol_id.asc()).all()
    scopes = db.session.query(Scope).order_by(Scope.scope_id.asc()).all()
    return render_template('component-' + page + '.html',
                           protocols=protocols, scopes=scopes, md=md, page=page)

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
    md.fw.mark_dirty()
    db.session.commit()

    # log
    flash('Removed requirement %s' % rq.value, 'info')
    return redirect(url_for('.firmware_component_show',
                            component_id=md.component_id,
                            page='requires'))

@app.route('/lvfs/component/<int:component_id>/requirement/add', methods=['POST'])
@app.route('/lvfs/component/<int:component_id>/requirement/modify', methods=['POST'])
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
    if 'modify' in request.url_rule.rule:
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
    md.fw.mark_dirty()
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
    md.fw.mark_dirty()
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
    md.fw.mark_dirty()
    db.session.commit()
    flash('Added keywords', 'info')
    return redirect(url_for('.firmware_component_show',
                            component_id=md.component_id,
                            page='keywords'))
@app.route('/lvfs/component/<int:component_id>/checksum/delete/<checksum_id>')
@login_required
def firmware_checksum_delete(component_id, checksum_id):

    # get firmware component
    csum = db.session.query(Checksum).filter(Checksum.checksum_id == checksum_id).first()
    if not csum:
        return _error_internal('No checksum matched!')

    # get the component for the checksum
    md = csum.md
    if md.component_id != component_id:
        return _error_internal('Wrong component ID for checksum!')
    if not md:
        return _error_internal('No metadata matched!')

    # security check
    if not md.check_acl('@modify-checksums'):
        return _error_permission_denied('Unable to modify other vendor firmware')

    # remove chid
    md.fw.mark_dirty()
    db.session.delete(csum)
    db.session.commit()

    # log
    flash('Removed checksum %s' % csum.value, 'info')
    return redirect(url_for('.firmware_component_show',
                            component_id=md.component_id,
                            page='checksums'))

@app.route('/lvfs/component/<int:component_id>/checksum/add', methods=['POST'])
@login_required
def firmware_checksum_add(component_id):
    """ Adds a checksum to a component """

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
    if not md.check_acl('@modify-checksums'):
        return _error_permission_denied('Unable to modify other vendor firmware')

    # validate is a valid hash
    hash_value = request.form['value']
    if _is_sha1(hash_value):
        hash_kind = 'SHA1'
    elif _is_sha256(hash_value):
        hash_kind = 'SHA256'
    else:
        flash('%s is not a recognised SHA1 or SHA256 hash' % hash_value, 'warning')
        return redirect(url_for('.firmware_component_show',
                                component_id=md.component_id,
                                page='checksums'))

    # check it's not already been added
    for csum in md.device_checksums:
        if csum.value == hash_value:
            flash('%s has already been added' % hash_value, 'warning')
            return redirect(url_for('.firmware_component_show',
                                    component_id=md.component_id,
                                    page='checksums'))

    # add checksum
    csum = Checksum(kind=hash_kind, value=hash_value)
    md.device_checksums.append(csum)
    md.fw.mark_dirty()
    db.session.commit()
    flash('Added device checksum', 'info')
    return redirect(url_for('.firmware_component_show',
                            component_id=md.component_id,
                            page='checksums'))
