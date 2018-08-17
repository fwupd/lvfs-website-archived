#!/usr/bin/python2
# -*- coding: utf-8 -*-
#
# Copyright (C) 2018 Richard Hughes <richard@hughsie.com>
# Licensed under the GNU General Public License Version 2

import json

from flask import request, url_for, redirect, flash, Response
from flask_login import login_required

from app import app, db

from .models import Firmware, Report, ReportAttribute, Issue
from .util import _error_internal, _error_permission_denied
from .util import _json_success, _json_error

@app.route('/lvfs/report/<report_id>')
@login_required
def report_view(report_id):
    report = db.session.query(Report).filter(Report.report_id == report_id).first()
    if not report:
        return _error_permission_denied('Report does not exist')
    # security check
    if not report.check_acl('@view'):
        return _error_permission_denied('Unable to view report')
    return Response(response=str(report.to_kvs()),
                    status=400, \
                    mimetype="application/json")

@app.route('/lvfs/report/<report_id>/delete')
@login_required
def report_delete(report_id):
    report = db.session.query(Report).filter(Report.report_id == report_id).first()
    if not report:
        return _error_internal('No report found!')
    # security check
    if not report.check_acl('@delete'):
        return _error_permission_denied('Unable to delete report')
    for e in report.attributes:
        db.session.delete(e)
    db.session.delete(report)
    db.session.commit()
    flash('Deleted report', 'info')
    return redirect(url_for('.analytics_reports'))

def _find_issue_for_report_data(data, fw):
    for issue in db.session.query(Issue).order_by(Issue.priority.desc()).all():
        if not issue.enabled:
            continue
        if issue.vendor_id != 1 and issue.vendor_id != fw.vendor_id:
            continue
        if issue.matches(data):
            return issue
    return None

@app.route('/lvfs/firmware/report', methods=['POST'])
def firmware_report():
    """ Upload a report """

    # only accept form data
    if request.method != 'POST':
        return _json_error('only POST supported')

    # parse JSON data
    try:
        item = json.loads(request.data.decode('utf8'))
    except ValueError as e:
        return _json_error(str(e))

    # check we got enough data
    for key in ['ReportVersion', 'MachineId', 'Reports', 'Metadata']:
        if not key in item:
            return _json_error('invalid data, expected %s' % key)
        if item[key] is None:
            return _json_error('missing data, expected %s' % key)

    # parse only this version
    if item['ReportVersion'] != 2:
        return _json_error('report version not supported')

    # add each firmware report
    machine_id = item['MachineId']
    reports = item['Reports']
    if len(reports) == 0:
        return _json_error('no reports included')
    metadata = item['Metadata']
    if len(metadata) == 0:
        return _json_error('no metadata included')

    msgs = []
    uris = []
    for report in reports:
        for key in ['Checksum', 'UpdateState', 'Metadata']:
            if not key in report:
                return _json_error('invalid data, expected %s' % key)
            if report[key] is None:
                return _json_error('missing data, expected %s' % key)

        # flattern the report including the per-machine and per-report metadata
        data = metadata
        for key in report:
            # don't store some data
            if key in ['Created', 'Modified', 'BootTime', 'UpdateState',
                       'DeviceId', 'UpdateState', 'DeviceId', 'Checksum']:
                continue
            if key == 'Metadata':
                md = report[key]
                for md_key in md:
                    data[md_key] = md[md_key]
                continue
            data[key] = unicode(report[key]).encode('ascii', 'ignore')

        # try to find the checksum_upload (which might not exist on this server)
        fw = db.session.query(Firmware).filter(Firmware.checksum_signed == report['Checksum']).first()
        if not fw:
            msgs.append('%s did not match any known firmware archive' % report['Checksum'])
            continue

        # find any matching report
        issue_id = 0
        if report['UpdateState'] == 3:
            issue = _find_issue_for_report_data(data, fw)
            if issue:
                issue_id = issue.issue_id
                msgs.append('The failure is a known issue')
                uris.append(issue.url)

        # update any old report
        r = db.session.query(Report).\
                        filter(Report.checksum == report['Checksum']).\
                        filter(Report.machine_id == machine_id).first()
        if r:
            msgs.append('%s replaces old report' % report['Checksum'])
            r.state = report['UpdateState']
            for e in r.attributes:
                db.session.delete(e)
        else:
            # save a new report in the database
            r = Report(machine_id=machine_id,
                       firmware_id=fw.firmware_id,
                       issue_id=issue_id,
                       state=report['UpdateState'],
                       checksum=report['Checksum'])

        # save all the report entries
        for key in data:
            r.attributes.append(ReportAttribute(key=key, value=data[key]))
        db.session.add(r)

    # all done
    db.session.commit()

    # put messages and URIs on one line
    return _json_success(msg='; '.join(msgs) if msgs else None,
                         uri='; '.join(uris) if uris else None)
