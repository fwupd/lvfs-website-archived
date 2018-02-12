#!/usr/bin/python2
# -*- coding: utf-8 -*-
#
# Copyright (C) 2018 Richard Hughes <richard@hughsie.com>
# Licensed under the GNU General Public License Version 2

import json

from flask import request, url_for, redirect, flash, Response, g
from flask_login import login_required

from app import app, db

from .models import Firmware, Report, Issue, UserCapability
from .util import _error_internal, _error_permission_denied

@app.route('/lvfs/report/<report_id>')
@login_required
def report_view(report_id):
    if not g.user.check_capability(UserCapability.Admin):
        return _error_permission_denied('Unable to view report')
    rprt = db.session.query(Report).filter(Report.id == report_id).first()
    if not rprt:
        return _error_permission_denied('Report does not exist')
    return Response(response=rprt.json,
                    status=400, \
                    mimetype="application/json")

@app.route('/lvfs/report/<report_id>/delete')
@login_required
def report_delete(report_id):
    if not g.user.check_capability(UserCapability.Admin):
        return _error_permission_denied('Unable to view report')
    report = db.session.query(Report).filter(Report.id == report_id).first()
    if not report:
        return _error_internal('No report found!')
    db.session.delete(report)
    db.session.commit()
    flash('Deleted report', 'info')
    return redirect(url_for('.analytics_reports'))

def json_success(msg=None, uri=None, errcode=200):
    """ Success handler: JSON output """
    item = {}
    item['success'] = True
    if msg:
        item['msg'] = msg
    if uri:
        item['uri'] = uri
    dat = json.dumps(item, sort_keys=True, indent=4, separators=(',', ': '))
    return Response(response=dat,
                    status=errcode, \
                    mimetype="application/json")

@app.errorhandler(400)
def json_error(msg=None, errcode=400):
    """ Error handler: JSON output """
    item = {}
    item['success'] = False
    if msg:
        item['msg'] = str(msg)
    dat = json.dumps(item, sort_keys=True, indent=4, separators=(',', ': '))
    return Response(response=dat,
                    status=errcode, \
                    mimetype="application/json")

def _do_all_contitions_match(issue, data):
    for condition in issue.conditions:
        if not condition.key in data:
            return False
        if not condition.matches(data[condition.key]):
            return False
    return True

def _find_issue_for_report_data(data, fw):
    for issue in db.session.query(Issue).all():
        if not issue.enabled:
            continue
        if issue.group_id != 'admin' and issue.group_id != fw.group_id:
            continue
        if _do_all_contitions_match(issue, data):
            return issue
    return None

@app.route('/lvfs/firmware/report', methods=['POST'])
def firmware_report():
    """ Upload a report """

    # only accept form data
    if request.method != 'POST':
        return json_error('only POST supported')

    # parse JSON data
    try:
        item = json.loads(request.data.decode('utf8'))
    except ValueError as e:
        return json_error(str(e))

    # check we got enough data
    for key in ['ReportVersion', 'MachineId', 'Reports', 'Metadata']:
        if not key in item:
            return json_error('invalid data, expected %s' % key)
        if item[key] is None:
            return json_error('missing data, expected %s' % key)

    # parse only this version
    if item['ReportVersion'] != 2:
        return json_error('report version not supported')

    # add each firmware report
    machine_id = item['MachineId']
    reports = item['Reports']
    if len(reports) == 0:
        return json_error('no reports included')
    metadata = item['Metadata']
    if len(metadata) == 0:
        return json_error('no metadata included')

    msgs = []
    uris = []
    for report in reports:
        for key in ['Checksum', 'UpdateState', 'Metadata']:
            if not key in report:
                return json_error('invalid data, expected %s' % key)
            if report[key] is None:
                return json_error('missing data, expected %s' % key)
        checksum = report['Checksum']
        report_metadata = report['Metadata']

        # try to find the firmware_id (which might not exist on this server)
        fw = db.session.query(Firmware).filter(Firmware.checksum == checksum).first()
        if not fw:
            msgs.append('%s did not match any known firmware archive' % checksum)
            continue

        # copy shared metadata and dump to JSON
        for key in metadata:
            if key in report_metadata:
                continue
            report_metadata[key] = metadata[key]
        json_raw = json.dumps(report, sort_keys=True,
                              indent=2, separators=(',', ': '))

        # find any matching report
        issue_id = 0
        if report['UpdateState'] == 3:
            issue_data = report_metadata
            issue_data['MachineId'] = item['MachineId']
            for key in ['VersionNew', 'VersionOld', 'Plugin', 'UpdateError', 'Guid']:
                if key in report:
                    issue_data[key] = report[key]
            issue = _find_issue_for_report_data(issue_data, fw)
            if issue:
                msgs.append('The failure is a known issue')
                uris.append(issue.url)

        # update any old report
        report_old = db.session.query(Report).\
                        filter(Report.checksum == checksum).\
                        filter(Report.machine_id == machine_id).first()
        if report_old:
            msgs.append('%s replaces old report' % checksum)
            report_old.state = report['UpdateState']
            report_old.json = json_raw
            continue

        # save a new report in the database
        db.session.add(Report(machine_id=machine_id,
                              firmware_id=fw.firmware_id,
                              issue_id=issue_id,
                              state=report['UpdateState'],
                              checksum=checksum,
                              json=json_raw))

    # all done
    db.session.commit()

    # put messages and URIs on one line
    return json_success(msg='; '.join(msgs) if msgs else None,
                        uri='; '.join(uris) if uris else None)
