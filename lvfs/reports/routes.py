#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2018 Richard Hughes <richard@hughsie.com>
#
# SPDX-License-Identifier: GPL-2.0+

import json
from typing import Optional, Dict, List

from flask import Blueprint, request, url_for, redirect, flash, Response, render_template
from flask_login import login_required

from celery.schedules import crontab

from lvfs import app, db, csrf, tq

from lvfs.components.models import ComponentChecksum
from lvfs.firmware.models import Firmware
from lvfs.issues.models import Issue
from lvfs.users.models import UserCertificate
from lvfs.util import _event_log
from lvfs.util import _json_success, _json_error, _pkcs7_signature_info, _pkcs7_signature_verify
from lvfs.hash import _is_sha1, _is_sha256

from .models import Report, ReportAttribute
from .utils import _async_regenerate_reports

bp_reports = Blueprint('reports', __name__, template_folder='templates')

@tq.on_after_finalize.connect
def setup_periodic_tasks(sender, **_):
    sender.add_periodic_task(
        crontab(hour=5, minute=0),
        _async_regenerate_reports.s(),
    )

def _report_to_dict(report: Report) -> dict:
    data: Dict[str, str] = {}
    if report.state == 1:
        data['UpdateState'] = 'pending'
    elif report.state == 2:
        data['UpdateState'] = 'success'
    elif report.state == 3:
        data['UpdateState'] = 'failed'
    elif report.state == 4:
        data['UpdateState'] = 'needs-reboot'
    else:
        data['UpdateState'] = 'unknown'
    if report.machine_id:
        data['MachineId'] = report.machine_id
    if report.firmware_id:
        data['FirmwareId'] = report.firmware_id
    for attr in report.attributes:
        data[attr.key] = attr.value
    return data

@bp_reports.route('/<report_id>')
@login_required
def route_view(report_id):
    report = db.session.query(Report).filter(Report.report_id == report_id).first()
    if not report:
        return _json_error('Report does not exist')
    # security check
    if not report.check_acl('@view'):
        return _json_error('Permission denied: Unable to view report')
    response = json.dumps(_report_to_dict(report), indent=4, separators=(',', ': '))
    return Response(response=response,
                    status=400, \
                    mimetype="application/json")

@bp_reports.route('/<report_id>/details')
@login_required
def route_show(report_id):
    report = db.session.query(Report).filter(Report.report_id == report_id).first()
    if not report:
        flash('Report does not exist', 'danger')
        return redirect(url_for('main.route_dashboard'))
    # security check
    if not report.check_acl('@view'):
        flash('Permission denied: Unable to view report', 'danger')
        return redirect(url_for('main.route_dashboard'))
    return render_template('report-details.html', rpt=report)

@bp_reports.route('/<report_id>/delete', methods=['POST'])
@login_required
def route_delete(report_id):
    report = db.session.query(Report).filter(Report.report_id == report_id).first()
    if not report:
        flash('No report found!', 'danger')
        return redirect(url_for('analytics.route_reports'))
    # security check
    if not report.check_acl('@delete'):
        flash('Permission denied: Unable to delete report', 'danger')
        return redirect(url_for('reports.route_show', report_id=report_id))
    for e in report.attributes:
        db.session.delete(e)
    db.session.delete(report)
    db.session.commit()
    flash('Deleted report', 'info')
    return redirect(url_for('analytics.route_reports'))

def _find_issue_for_report_data(data: dict, fw: Firmware) -> Optional[Issue]:
    for issue in db.session.query(Issue).order_by(Issue.priority.desc()):
        if not issue.enabled:
            continue
        if issue.vendor_id != 1 and issue.vendor_id != fw.vendor_id:
            continue
        if issue.matches(data):
            return issue
    return None

@app.route('/lvfs/firmware/report', methods=['POST'])
@csrf.exempt
def route_report():
    """ Upload a report """

    # only accept form data
    if request.method != 'POST':
        return _json_error('only POST supported')

    # parse both content types, either application/json or multipart/form-data
    signature = None
    if request.data:
        payload = request.data.decode('utf8')
    elif request.form:
        data = request.form.to_dict()
        if 'payload' not in data:
            return _json_error('No payload in multipart/form-data')
        payload = data['payload']
        if 'signature' in data:
            signature = data['signature']
    else:
        return _json_error('No data')

    # find user and verify
    crt = None
    if signature:
        try:
            info = _pkcs7_signature_info(signature)
        except IOError as e:
            return _json_error('Signature invalid: %s' % str(e))
        if 'serial' not in info:
            return _json_error('Signature invalid, no signature')
        crt = db.session.query(UserCertificate).filter(UserCertificate.serial == info['serial']).first()
        if crt:
            try:
                _pkcs7_signature_verify(crt.text, payload, signature)
            except IOError as _:
                return _json_error('Signature did not validate')

    # parse JSON data
    try:
        item = json.loads(payload)
    except ValueError as e:
        return _json_error('No JSON object could be decoded: ' + str(e))

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

    msgs: List[str] = []
    uris: List[str] = []
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
            # allow array of strings for any of the keys
            if isinstance(report[key], list):
                data[key] = ','.join(report[key])
            else:
                data[key] = report[key]

        # try to find the checksum (which might not exist on this server)
        fw = db.session.query(Firmware).filter(Firmware.checksum_signed_sha1 == report['Checksum']).first()
        if not fw:
            fw = db.session.query(Firmware).filter(Firmware.checksum_signed_sha256 == report['Checksum']).first()
        if not fw:
            msgs.append('%s did not match any known firmware archive' % report['Checksum'])
            continue

        # cannot report this failure
        if fw.do_not_track:
            msgs.append('%s will not accept reports' % report['Checksum'])
            continue

        # update the device checksums if there is only one component
        if crt and crt.user.check_acl('@qa') and 'ChecksumDevice' in data and len(fw.mds) == 1:
            md = fw.md_prio
            found = False

            # fwupd v1.2.6 sends an array of strings, before that just a string
            checksums = data['ChecksumDevice']
            if not isinstance(checksums, list):
                checksums = [checksums]

            # does the submitted checksum already exist as a device checksum
            for checksum in checksums:
                for csum in md.device_checksums:
                    if csum.value == checksum:
                        found = True
                        break
                if found:
                    continue
                _event_log('added device checksum %s to firmware %s' % (checksum, md.fw.checksum_upload_sha1))
                if _is_sha1(checksum):
                    md.device_checksums.append(ComponentChecksum(value=checksum, kind='SHA1'))
                elif _is_sha256(checksum):
                    md.device_checksums.append(ComponentChecksum(value=checksum, kind='SHA256'))

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
            for attr in r.attributes:
                db.session.delete(attr)
        else:
            # save a new report in the database
            r = Report(machine_id=machine_id,
                       firmware_id=fw.firmware_id,
                       issue_id=issue_id,
                       state=report['UpdateState'],
                       checksum=report['Checksum'])

        # update the firmware so that the QA user does not have to wait 24h
        if r.state == 2:
            fw.report_success_cnt += 1
        elif r.state == 3:
            if r.issue_id:
                fw.report_issue_cnt += 1
            else:
                fw.report_failure_cnt += 1

        # update the LVFS user
        if crt:
            r.user_id = crt.user_id

        # save all the report entries
        for key in data:
            r.attributes.append(ReportAttribute(key=key, value=data[key]))
        db.session.add(r)

    # all done
    db.session.commit()

    # put messages and URIs on one line
    return _json_success(msg='; '.join(msgs) if msgs else None,
                         uri='; '.join(uris) if uris else None)
