#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2017-2018 Richard Hughes <richard@hughsie.com>
#
# SPDX-License-Identifier: GPL-2.0+

from flask import Blueprint, request, url_for, redirect, render_template, flash, make_response
from flask_login import login_required

from sqlalchemy import func

from lvfs import db, ploader

from lvfs.models import Requirement, Component, ComponentIssue, Keyword, Checksum, Category
from lvfs.models import Protocol, Report, ReportAttribute, Firmware, Remote
from lvfs.util import _error_internal, _validate_guid
from lvfs.hash import _is_sha1, _is_sha256

bp_components = Blueprint('components', __name__, template_folder='templates')

def _sanitize_markdown_text(txt):
    txt = txt.replace('\r', '')
    new_lines = [line.strip() for line in txt.split('\n')]
    return '\n'.join(new_lines)

@bp_components.route('/problems')
@login_required
def route_problems():
    """
    Show all components with problems
    """
    mds = []
    for md in db.session.query(Component).\
                order_by(Component.release_timestamp.desc()):
        if not md.problems:
            continue
        if not md.check_acl('@modify-updateinfo'):
            continue
        if md.fw.is_deleted:
            continue
        mds.append(md)
    return render_template('component-problems.html',
                           category='firmware',
                           mds=mds)

@bp_components.route('/problems/<remote_name>')
@login_required
def route_problems_remote(remote_name):
    """
    Show all components with problems
    """
    mds = []
    for md in db.session.query(Component).join(Firmware).join(Remote).\
                filter(Remote.name == remote_name).\
                order_by(Component.release_timestamp.desc()):
        if not md.problems:
            continue
        mds.append(md)
    return render_template('component-problems.html',
                           category='firmware',
                           mds=mds)

@bp_components.route('/<int:component_id>/shards')
@login_required
def route_shards(component_id):
    """
    Show the shards of each component
    """

    # get firmware component
    md = db.session.query(Component).filter(Component.component_id == component_id).first()
    if not md:
        flash('No component matched!', 'danger')
        return redirect(url_for('firmware.route_firmware'))

    # security check
    fw = md.fw
    if not fw:
        flash('No component matched!', 'danger')
        return redirect(url_for('firmware.route_firmware'))
    if not fw.check_acl('@view'):
        flash('Permission denied: Unable to view component', 'danger')
        return redirect(url_for('components.route_show', component_id=component_id))

    return render_template('component-shards.html',
                           category='firmware',
                           md=md, page='shards')

@bp_components.route('/<int:component_id>/certificates')
@login_required
def route_certificates(component_id):
    """
    Show the shards of each component
    """

    # get firmware component
    md = db.session.query(Component).filter(Component.component_id == component_id).first()
    if not md:
        flash('No component matched!', 'danger')
        return redirect(url_for('firmware.route_firmware'))

    # security check
    fw = md.fw
    if not fw:
        flash('No firmware matched!', 'danger')
        return redirect(url_for('firmware.route_firmware'))
    if not fw.check_acl('@view'):
        flash('Permission denied: Unable to view component', 'danger')
        return redirect(url_for('components.route_show', component_id=component_id))

    return render_template('component-certificates.html',
                           category='firmware',
                           md=md, page='certificates')

@bp_components.route('/<int:component_id>/modify', methods=['POST'])
@login_required
def route_modify(component_id):
    """ Modifies the component properties """

    # find firmware
    md = db.session.query(Component).filter(Component.component_id == component_id).first()
    if not md:
        flash('No component matched!', 'danger')
        return redirect(url_for('firmware.route_firmware'))

    # security check
    if not md.check_acl('@modify-updateinfo'):
        flash('Permission denied: Insufficient permissions to modify firmware', 'danger')
        return redirect(url_for('components.route_show', component_id=component_id))

    # set new metadata values
    page = 'overview'
    retry_all_tests = False
    if 'screenshot_url' in request.form:
        md.screenshot_url = request.form['screenshot_url']
    if 'protocol_id' in request.form:
        if md.protocol_id != request.form['protocol_id']:
            md.protocol_id = request.form['protocol_id']
            retry_all_tests = True
    if 'category_id' in request.form:
        category_id = request.form['category_id']
        if not category_id:
            category_id = None
        if md.category_id != category_id:
            md.category_id = category_id
            retry_all_tests = True
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
    if 'appstream_id' in request.form:
        md.appstream_id = request.form['appstream_id']
    if 'name' in request.form:
        md.name = request.form['name']
    if 'name_variant_suffix' in request.form:
        md.name_variant_suffix = request.form['name_variant_suffix']
    if 'release_tag' in request.form:
        md.release_tag = request.form['release_tag']

    # the firmware changed protocol
    if retry_all_tests:
        for test in md.fw.tests:
            test.retry()

    # ensure the test has been added for the new firmware type
    ploader.ensure_test_for_fw(md.fw)

    # modify
    md.fw.mark_dirty()
    md.fw.signed_timestamp = None
    db.session.commit()
    flash('Component updated', 'info')
    return redirect(url_for('components.route_show',
                            component_id=component_id,
                            page=page))

@bp_components.route('/<int:component_id>/checksums')
@login_required
def route_checksums(component_id):
    """ Show firmware component information """

    # get firmware component
    md = db.session.query(Component).filter(Component.component_id == component_id).first()
    if not md:
        flash('No component matched!', 'danger')
        return redirect(url_for('firmware.route_firmware'))

    # security check
    fw = md.fw
    if not fw:
        flash('No firmware matched!', 'danger')
        return redirect(url_for('firmware.route_firmware'))
    if not fw.check_acl('@view'):
        flash('Permission denied: Unable to view component', 'danger')
        return redirect(url_for('components.route_show', component_id=component_id))

    # find reports witch device checksums that match this firmware
    checksum_counts = db.session.query(func.count(ReportAttribute.value),
                                       ReportAttribute.value).\
                                       join(Report).\
                                       filter(Report.state == 2).\
                                       filter(Report.firmware_id == fw.firmware_id).\
                                       filter(ReportAttribute.key == 'ChecksumDevice').\
                                       group_by(ReportAttribute.value).all()
    device_checksums = [csum.value for csum in md.device_checksums]
    return render_template('component-checksums.html',
                           category='firmware',
                           md=md, page='checksums',
                           device_checksums=device_checksums,
                           checksum_counts=checksum_counts)

@bp_components.route('/<int:component_id>')
@bp_components.route('/<int:component_id>/<page>')
@login_required
def route_show(component_id, page='overview'):
    """ Show firmware component information """

    # get firmware component
    md = db.session.query(Component).filter(Component.component_id == component_id).first()
    if not md:
        flash('No component matched!', 'danger')
        return redirect(url_for('firmware.route_firmware'))

    # security check
    fw = md.fw
    if not fw:
        flash('No firmware matched!', 'danger')
        return redirect(url_for('firmware.route_firmware'))
    if not fw.check_acl('@view'):
        flash('Permission denied: Unable to view other vendor firmware', 'danger')
        return redirect(url_for('components.route_show', component_id=component_id))

    # firmware requirements are too complicated to show on the simplified fiew
    if page == 'requires' and md.has_complex_requirements:
        page = 'requires-advanced'

    protocols = db.session.query(Protocol).order_by(Protocol.name.asc()).all()
    for protocol in protocols:
        if protocol.value == 'unknown':
            protocols.remove(protocol)
            protocols.insert(0, protocol)
            break
    categories = db.session.query(Category).order_by(Category.name.asc()).all()
    return render_template('component-' + page + '.html',
                           category='firmware',
                           protocols=protocols,
                           categories=categories,
                           md=md,
                           page=page)

@bp_components.route('/<int:component_id>/requirement/delete/<requirement_id>')
@login_required
def route_requirement_delete(component_id, requirement_id):

    # get firmware component
    rq = db.session.query(Requirement).filter(Requirement.requirement_id == requirement_id).first()
    if not rq:
        flash('No requirement matched!', 'danger')
        return redirect(url_for('components.route_show', component_id=component_id))

    # get the firmware for the requirement
    md = rq.md
    if md.component_id != component_id:
        return _error_internal('Wrong component ID for requirement!')
    if not md:
        return _error_internal('No metadata matched!')

    # security check
    if not md.check_acl('@modify-requirements'):
        flash('Permission denied: Unable to modify other vendor firmware', 'danger')
        return redirect(url_for('components.route_show', component_id=component_id))

    # remove chid
    db.session.delete(rq)
    md.fw.mark_dirty()
    md.fw.signed_timestamp = None
    db.session.commit()

    # log
    flash('Removed requirement %s' % rq.value, 'info')
    return redirect(url_for('components.route_show',
                            component_id=md.component_id,
                            page='requires'))

@bp_components.route('/<int:component_id>/requirement/create', methods=['POST'])
@login_required
def route_requirement_create(component_id):
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
        flash('No component matched!', 'danger')
        return redirect(url_for('firmware.route_firmware'))

    # security check
    if not md.check_acl('@modify-requirements'):
        flash('Permission denied: Unable to modify other vendor firmware', 'danger')
        return redirect(url_for('components.route_show', component_id=component_id))

    # validate CHID is a valid GUID
    if request.form['kind'] == 'hardware' and not _validate_guid(request.form['value']):
        flash('Cannot add requirement: %s is not a valid GUID' % request.form['value'], 'warning')
        return redirect(url_for('components.route_show',
                                component_id=md.component_id,
                                page='requires'))

    # support empty too
    compare = request.form.get('compare', None)
    if not compare:
        compare = None
    version = request.form.get('version', None)
    if not version:
        version = None
    depth = request.form.get('depth', None)
    if not depth:
        depth = None

    # add requirement
    rq = Requirement(kind=request.form['kind'],
                     value=request.form['value'].strip(),
                     compare=compare,
                     version=version,
                     depth=depth)
    md.requirements.append(rq)
    md.fw.mark_dirty()
    md.fw.signed_timestamp = None
    db.session.commit()
    flash('Added requirement', 'info')
    return redirect(url_for('components.route_show',
                            component_id=md.component_id,
                            page='requires'))

@bp_components.route('/<int:component_id>/requirement/modify', methods=['POST'])
@login_required
def route_requirement_modify(component_id):
    """ Adds a requirement to a component """

    # check we have data
    for key in ['kind', 'value']:
        if key not in request.form:
            return _error_internal('No %s specified!' % key)
    if request.form['kind'] not in ['hardware', 'firmware', 'id']:
        return _error_internal('No valid kind specified!')

    # get firmware component
    md = db.session.query(Component).\
            filter(Component.component_id == component_id).first()
    if not md:
        flash('No component matched!', 'danger')
        return redirect(url_for('firmware.route_firmware'))

    # security check
    if not md.check_acl('@modify-requirements'):
        flash('Permission denied: Unable to modify other vendor firmware', 'danger')
        return redirect(url_for('components.route_show', component_id=component_id))

    # validate CHID is a valid GUID
    if request.form['kind'] == 'hardware' and not _validate_guid(request.form['value']):
        flash('Cannot add requirement: %s is not a valid GUID' % request.form['value'], 'warning')
        return redirect(url_for('components.route_show',
                                component_id=md.component_id,
                                page='requires'))

    # empty string is None
    value = request.form['value']
    if not value:
        value = None

    # check it's not already been added
    rq = md.find_req(request.form['kind'], value)
    if rq:
        if 'version' in request.form:
            rq.version = request.form['version']
        if 'compare' in request.form:
            if request.form['compare'] == 'any':
                db.session.delete(rq)
                db.session.commit()
                flash('Deleted requirement %s' % rq.value, 'info')
                return redirect(url_for('components.route_show',
                                        component_id=md.component_id,
                                        page='requires'))
            rq.compare = request.form['compare']
        db.session.commit()
        if rq.value:
            flash('Modified requirement %s' % rq.value, 'info')
        else:
            flash('Modified requirement firmware', 'info')
        return redirect(url_for('components.route_show',
                                component_id=md.component_id,
                                page='requires'))

    # add requirement
    rq = Requirement(kind=request.form['kind'],
                     value=value,
                     compare=request.form.get('compare', None),
                     version=request.form.get('version', None),
                     depth=request.form.get('depth', None),
                    )
    md.requirements.append(rq)
    md.fw.mark_dirty()
    md.fw.signed_timestamp = None
    db.session.commit()
    flash('Added requirement', 'info')
    return redirect(url_for('components.route_show',
                            component_id=md.component_id,
                            page='requires'))

@bp_components.route('/<int:component_id>/keyword/<keyword_id>/delete')
@login_required
def route_keyword_delete(component_id, keyword_id):

    # get firmware component
    kw = db.session.query(Keyword).filter(Keyword.keyword_id == keyword_id).first()
    if not kw:
        flash('No keyword matched!', 'danger')
        return redirect(url_for('components.route_show', component_id=component_id))

    # get the firmware for the keyword
    md = kw.md
    if md.component_id != component_id:
        return _error_internal('Wrong component ID for keyword!')
    if not md:
        return _error_internal('No metadata matched!')

    # security check
    if not md.check_acl('@modify-keywords'):
        flash('Permission denied: Unable to modify other vendor firmware', 'danger')
        return redirect(url_for('components.route_show', component_id=component_id))

    # remove chid
    db.session.delete(kw)
    md.fw.mark_dirty()
    md.fw.signed_timestamp = None
    db.session.commit()

    # log
    flash('Removed keyword %s' % kw.value, 'info')
    return redirect(url_for('components.route_show',
                            component_id=md.component_id,
                            page='keywords'))

@bp_components.route('/<int:component_id>/keyword/create', methods=['POST'])
@login_required
def route_keyword_create(component_id):
    """ Adds one or more keywords to the existing component """

    # check we have data
    for key in ['value']:
        if key not in request.form or not request.form[key]:
            return _error_internal('No %s specified!' % key)

    # get firmware component
    md = db.session.query(Component).\
            filter(Component.component_id == component_id).first()
    if not md:
        flash('No component matched!', 'danger')
        return redirect(url_for('firmware.route_firmware'))

    # security check
    if not md.check_acl('@modify-keywords'):
        flash('Permission denied: Unable to modify other vendor firmware', 'danger')
        return redirect(url_for('components.route_show', component_id=component_id))

    # add keyword
    md.add_keywords_from_string(request.form['value'])
    md.fw.mark_dirty()
    md.fw.signed_timestamp = None
    db.session.commit()
    flash('Added keywords', 'info')
    return redirect(url_for('components.route_show',
                            component_id=md.component_id,
                            page='keywords'))

@bp_components.route('/<int:component_id>/issue/<component_issue_id>/delete')
@login_required
def route_issue_delete(component_id, component_issue_id):

    # get firmware component
    issue = db.session.query(ComponentIssue).\
            filter(Component.component_id == component_id,
                   ComponentIssue.component_issue_id == component_issue_id).first()
    if not issue:
        flash('No issue matched!', 'danger')
        return redirect(url_for('components.route_show', component_id=component_id))

    # permission check
    md = issue.md
    if not md.check_acl('@modify-updateinfo'):
        flash('Permission denied: Unable to modify firmware', 'danger')
        return redirect(url_for('components.route_show', component_id=component_id))

    # remove issue
    db.session.delete(issue)
    md.fw.mark_dirty()
    md.fw.signed_timestamp = None
    db.session.commit()

    # log
    flash('Removed {}'.format(issue.value), 'info')
    return redirect(url_for('components.route_show',
                            component_id=md.component_id,
                            page='issues'))

def _autoimport_issues(md, prefix, kind):
    issues = []
    start = 0
    tmp = md.release_description
    description_new = ''

    while True:

        # look for a CVE token
        idx = tmp.find(prefix, start)
        if idx == -1:
            description_new += tmp[start:]
            break

        # yay, so save what we've got so far
        description_new += tmp[start:idx]

        # find the end of the CVE value
        issue_len = 0
        for char in tmp[idx+len(prefix):]:
            if char != '-' and not char.isnumeric():
                break
            issue_len += 1

        # extract the CVE value, and add to the component if required
        value = tmp[idx:idx + len(prefix) + issue_len]
        if value not in md.issue_values:
            issue = ComponentIssue(kind=kind, value=value)
            if issue.problem:
                description_new += value
            else:
                issues.append(issue)

        # advance string to end of CVE number
        start = idx + len(prefix) + issue_len

    # success
    if issues:
        for empty in ['()', '( )', '(  )', '(   )', '(    )',
                      '(,)', '(, , )', '(, , , )', '(, , , , )',
                      '( & )']:
            description_new = description_new.replace(empty, '')
        description_new = description_new.replace(' \n', '\n')
        md.release_description = description_new
        md.issues.extend(issues)

    return len(issues)

@bp_components.route('/<int:component_id>/issue/autoimport')
@login_required
def route_issue_autoimport(component_id):

    # get firmware component
    md = db.session.query(Component).\
            filter(Component.component_id == component_id).first()
    if not md:
        flash('No component matched!', 'danger')
        return redirect(url_for('firmware.route_firmware'))

    # permission check
    if not md.check_acl('@modify-updateinfo'):
        flash('Permission denied: Unable to modify firmware', 'danger')
        return redirect(url_for('components.route_show', component_id=component_id))

    # find any valid CVE numbers in the existing description
    n_issues = _autoimport_issues(md, 'CVE-', 'cve')
    n_issues += _autoimport_issues(md, 'DSA-', 'dell')
    n_issues += _autoimport_issues(md, 'LEN-', 'lenovo')
    n_issues += _autoimport_issues(md, 'INTEL-SA-', 'intel')

    # success
    if not n_issues:
        flash('No issues could be detected', 'info')
    else:
        md.fw.mark_dirty()
        md.fw.signed_timestamp = None
        db.session.commit()
        flash('Added {} issues — now review the update description for sanity'.format(n_issues), 'info')
    return redirect(url_for('components.route_show',
                            component_id=md.component_id,
                            page='update'))

@bp_components.route('/<int:component_id>/issue/create', methods=['POST'])
@login_required
def route_issue_create(component_id):
    """ Adds one or more CVEs to the existing component """

    # check we have data
    for key in ['value']:
        if key not in request.form or not request.form[key]:
            return _error_internal('No %s specified!' % key)

    # get firmware component
    md = db.session.query(Component).\
            filter(Component.component_id == component_id).first()
    if not md:
        flash('No component matched!', 'danger')
        return redirect(url_for('firmware.route_firmware'))

    # security check
    if not md.check_acl('@modify-updateinfo'):
        flash('Permission denied: Unable to modify firmware', 'danger')
        return redirect(url_for('components.route_show', component_id=component_id))

    # add issue
    for value in request.form['value'].split(','):
        if value in md.issue_values:
            flash('Already exists: {}'.format(value), 'info')
            continue
        if value.startswith('CVE-'):
            issue = ComponentIssue(kind='cve', value=value)
        elif value.startswith('DSA-'):
            issue = ComponentIssue(kind='dell', value=value)
        elif value.startswith('LEN-'):
            issue = ComponentIssue(kind='lenovo', value=value)
        elif value.startswith('INTEL-SA-'):
            issue = ComponentIssue(kind='intel', value=value)
        else:
            flash('Issue invalid: {}'.format(value), 'danger')
            return redirect(url_for('components.route_show',
                                    component_id=component_id,
                                    page='issues'))
        if issue.problem:
            flash('Issue invalid: {}'.format(issue.problem.description), 'danger')
            return redirect(url_for('components.route_show',
                                    component_id=component_id,
                                    page='issues'))
        flash('Added {}'.format(value), 'info')
        md.issues.append(issue)
    md.fw.mark_dirty()
    md.fw.signed_timestamp = None
    db.session.commit()
    return redirect(url_for('components.route_show',
                            component_id=md.component_id,
                            page='issues'))

@bp_components.route('/<int:component_id>/checksum/delete/<checksum_id>')
@login_required
def route_checksum_delete(component_id, checksum_id):

    # get firmware component
    csum = db.session.query(Checksum).filter(Checksum.checksum_id == checksum_id).first()
    if not csum:
        flash('No checksum matched!', 'danger')
        return redirect(url_for('components.route_show', component_id=component_id))

    # get the component for the checksum
    md = csum.md
    if md.component_id != component_id:
        flash('Wrong component ID for checksum', 'danger')
        return redirect(url_for('components.route_show', component_id=component_id))
    if not md:
        return _error_internal('No metadata matched!')

    # security check
    if not md.check_acl('@modify-checksums'):
        flash('Permission denied: Unable to modify other vendor firmware', 'danger')
        return redirect(url_for('components.route_show', component_id=component_id))

    # remove chid
    md.fw.mark_dirty()
    md.fw.signed_timestamp = None
    db.session.delete(csum)
    db.session.commit()

    # log
    flash('Removed device checksum', 'info')
    return redirect(url_for('components.route_show',
                            component_id=md.component_id,
                            page='checksums'))

@bp_components.route('/<int:component_id>/checksum/create', methods=['POST'])
@login_required
def route_checksum_create(component_id):
    """ Adds a checksum to a component """

    # check we have data
    for key in ['value']:
        if key not in request.form or not request.form[key]:
            return _error_internal('No %s specified!' % key)

    # get firmware component
    md = db.session.query(Component).\
            filter(Component.component_id == component_id).first()
    if not md:
        flash('No component matched!', 'danger')
        return redirect(url_for('firmware.route_firmware'))

    # security check
    if not md.check_acl('@modify-checksums'):
        flash('Permission denied: Unable to modify other vendor firmware', 'danger')
        return redirect(url_for('components.route_show', component_id=component_id))

    # validate is a valid hash
    hash_value = request.form['value']
    if _is_sha1(hash_value):
        hash_kind = 'SHA1'
    elif _is_sha256(hash_value):
        hash_kind = 'SHA256'
    else:
        flash('%s is not a recognised SHA1 or SHA256 hash' % hash_value, 'warning')
        return redirect(url_for('components.route_show',
                                component_id=md.component_id,
                                page='checksums'))

    # check it's not already been added
    for csum in md.device_checksums:
        if csum.value == hash_value:
            flash('%s has already been added' % hash_value, 'warning')
            return redirect(url_for('components.route_show',
                                    component_id=md.component_id,
                                    page='checksums'))

    # add checksum
    csum = Checksum(kind=hash_kind, value=hash_value)
    md.device_checksums.append(csum)
    md.fw.mark_dirty()
    md.fw.signed_timestamp = None
    db.session.commit()
    flash('Added device checksum', 'info')
    return redirect(url_for('components.route_show',
                            component_id=md.component_id,
                            page='checksums'))

@bp_components.route('/<int:component_id>/download')
@login_required
def route_download(component_id):

    # get firmware component
    md = db.session.query(Component).\
            filter(Component.component_id == component_id).first()
    if not md:
        flash('No component matched!', 'danger')
        return redirect(url_for('firmware.route_firmware'))
    if not md.fw.check_acl('@view'):
        flash('Permission denied: Unable to download component', 'danger')
        return redirect(url_for('main.route_dashboard'))
    if not md.blob:
        flash('Permission denied: Component has no data', 'warning')
        return redirect(url_for('main.route_dashboard'))
    response = make_response(md.blob)
    response.headers.set('Content-Type', 'application/octet-stream')
    response.headers.set('Content-Disposition', 'attachment', filename=md.filename_contents)
    return response
