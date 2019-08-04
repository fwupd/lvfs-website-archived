#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2018 Richard Hughes <richard@hughsie.com>
#
# SPDX-License-Identifier: GPL-2.0+

import json

from flask import request, url_for, redirect, flash, Response, render_template
from flask_login import login_required

from lvfs import app, db, csrf

from .models import Firmware, Report, ReportAttribute, Issue, Certificate, Checksum
from .util import _event_log
from .util import _json_success, _json_error, _pkcs7_signature_info, _pkcs7_signature_verify
from .hash import _is_sha1, _is_sha256

@app.route('/lvfs/report/<report_id>')
@login_required
def report_view(report_id):
    report = db.session.query(Report).filter(Report.report_id == report_id).first()
    if not report:
        return _json_error('Report does not exist')
    # security check
    if not report.check_acl('@view'):
        return _json_error('Permission denied: Unable to view report')
    return Response(response=str(report.to_kvs()),
                    status=400, \
                    mimetype="application/json")

@app.route('/lvfs/report/<report_id>/details')
@login_required
def report_details(report_id):
    report = db.session.query(Report).filter(Report.report_id == report_id).first()
    if not report:
        flash('Report does not exist', 'danger')
        return redirect(url_for('.dashboard'))
    # security check
    if not report.check_acl('@view'):
        flash('Permission denied: Unable to view report', 'danger')
        return redirect(url_for('.dashboard'))
    return render_template('report-details.html', rpt=report)

@app.route('/lvfs/report/<report_id>/delete')
@login_required
def report_delete(report_id):
    report = db.session.query(Report).filter(Report.report_id == report_id).first()
    if not report:
        flash('No report found!', 'danger')
        return redirect(url_for('.analytics_reports'))
    # security check
    if not report.check_acl('@delete'):
        flash('Permission denied: Unable to delete report', 'danger')
        return redirect(url_for('.report_details', report_id=report_id))
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
@csrf.exempt
def firmware_report():
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
            info = _pkcs7_signature_info(signature, check_rc=False)
        except IOError as e:
            return _json_error('Signature invalid: %s' % str(e))
        crt = db.session.query(Certificate).filter(Certificate.serial == info['serial']).first()
        if crt:
            try:
                _pkcs7_signature_verify(crt, payload, signature)
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
            # allow array of strings for any of the keys
            if isinstance(report[key], list):
                data[key] = ','.join(report[key])
            else:
                data[key] = report[key]

        # try to find the checksum_upload (which might not exist on this server)
        fw = db.session.query(Firmware).filter(Firmware.checksum_signed == report['Checksum']).first()
        if not fw:
            msgs.append('%s did not match any known firmware archive' % report['Checksum'])
            continue

        # cannot report this failure
        if fw.do_not_track:
            msgs.append('%s will not accept reports' % report['Checksum'])
            continue

        # update the device checksums if there is only one component
        if crt and crt.user.is_qa and 'ChecksumDevice' in data and len(fw.mds) == 1:
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
                _event_log('added device checksum %s to firmware %s' % (checksum, md.fw.checksum_upload))
                if _is_sha1(checksum):
                    md.device_checksums.append(Checksum(checksum, 'SHA1'))
                elif _is_sha256(checksum):
                    md.device_checksums.append(Checksum(checksum, 'SHA256'))

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
