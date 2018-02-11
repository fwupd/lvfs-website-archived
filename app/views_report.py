#!/usr/bin/python2
# -*- coding: utf-8 -*-
#
# Copyright (C) 2018 Richard Hughes <richard@hughsie.com>
# Licensed under the GNU General Public License Version 2

import json

from flask import request, url_for, redirect, flash, Response, g
from flask_login import login_required

from app import app, db

from .models import Firmware, Report, UserCapability
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

def json_success(msg=None, errcode=200):
    """ Success handler: JSON output """
    item = {}
    item['success'] = True
    if msg:
        item['msg'] = msg
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
        item['msg'] = msg
    dat = json.dumps(item, sort_keys=True, indent=4, separators=(',', ': '))
    return Response(response=dat,
                    status=errcode, \
                    mimetype="application/json")

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
                              state=report['UpdateState'],
                              checksum=checksum,
                              json=json_raw))

    # all done
    db.session.commit()

    # get a message on one line
    if len(msgs) > 0:
        return json_success('\n'.join(msgs))

    # no messages to report
    return json_success()
