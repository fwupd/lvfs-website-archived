#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2018-2020 Richard Hughes <richard@hughsie.com>
#
# SPDX-License-Identifier: GPL-2.0+

import json

from flask import Blueprint, request, url_for, redirect, flash, Response, render_template
from flask_login import login_required

from lvfs import db, csrf

from lvfs.hash import _is_sha256
from lvfs.models import HsiReport, HsiReportAttr
from lvfs.util import admin_login_required, _pkcs7_signature_info
from lvfs.util import _json_success, _json_error

bp_hsireports = Blueprint('hsireports', __name__, template_folder='templates')

@bp_hsireports.route('/')
@login_required
@admin_login_required
def route_list():
    rpts = db.session.query(HsiReport)\
                     .order_by(HsiReport.timestamp.desc())\
                     .limit(100).all()
    return render_template('hsireport-list.html',
                           category='admin',
                           rpts_filter=None,
                           rpts=rpts)

@bp_hsireports.route('/vendor/<host_vendor>')
@login_required
@admin_login_required
def route_vendor_show(host_vendor):
    rpts = db.session.query(HsiReport)\
                     .filter(HsiReport.host_vendor == host_vendor)\
                     .order_by(HsiReport.timestamp.desc())\
                     .limit(100).all()
    return render_template('hsireport-list.html',
                           category='admin',
                           rpts_filter=host_vendor,
                           rpts=rpts)

@bp_hsireports.route('/product/<host_product>')
@login_required
@admin_login_required
def route_product_show(host_product):
    rpts = db.session.query(HsiReport)\
                     .filter(HsiReport.host_product == host_product)\
                     .order_by(HsiReport.timestamp.desc())\
                     .limit(100).all()
    return render_template('hsireport-list.html',
                           category='admin',
                           rpts_filter=host_product,
                           rpts=rpts)

@bp_hsireports.route('/sku/<host_sku>')
@login_required
@admin_login_required
def route_sku_show(host_sku):
    rpts = db.session.query(HsiReport)\
                     .filter(HsiReport.host_sku == host_sku)\
                     .order_by(HsiReport.timestamp.desc())\
                     .limit(100).all()
    return render_template('hsireport-list.html',
                           category='admin',
                           rpts_filter=host_sku,
                           rpts=rpts)

@bp_hsireports.route('/family/<host_family>')
@login_required
@admin_login_required
def route_family_show(host_family):
    rpts = db.session.query(HsiReport)\
                     .filter(HsiReport.host_family == host_family)\
                     .order_by(HsiReport.timestamp.desc())\
                     .limit(100).all()
    return render_template('hsireport-list.html',
                           category='admin',
                           rpts_filter=host_family,
                           rpts=rpts)

@bp_hsireports.route('/<int:hsi_report_id>')
@login_required
def route_show(hsi_report_id):
    rpt = db.session.query(HsiReport).filter(HsiReport.hsi_report_id == hsi_report_id).first()
    if not rpt:
        flash('HsiReport does not exist', 'danger')
        return redirect(url_for('main.route_dashboard'))
    # security check
    if not rpt.check_acl('@view'):
        flash('Permission denied: Unable to view report', 'danger')
        return redirect(url_for('main.route_dashboard'))
    return render_template('hsireport-details.html',
                           category='admin',
                           rpt=rpt)

@bp_hsireports.route('/<int:hsi_report_id>/raw')
@login_required
def route_view(hsi_report_id):
    rpt = db.session.query(HsiReport).filter(HsiReport.hsi_report_id == hsi_report_id).first()
    if not rpt:
        return _json_error('HsiReport does not exist')
    # security check
    if not rpt.check_acl('@view'):
        flash('Permission denied: Unable to view report', 'danger')
        return redirect(url_for('main.route_dashboard'))
    return Response(response=str(rpt.to_kvs()),
                    status=400, \
                    mimetype="application/json")

@bp_hsireports.route('/<int:hsi_report_id>/delete')
@login_required
def route_delete(hsi_report_id):
    rpt = db.session.query(HsiReport).filter(HsiReport.hsi_report_id == hsi_report_id).first()
    if not rpt:
        flash('No report found!', 'danger')
        return redirect(url_for('analytics.route_hsireports'))
    # security check
    if not rpt.check_acl('@delete'):
        flash('Permission denied: Unable to delete report', 'danger')
        return redirect(url_for('hsireports.route_show', hsi_report_id=hsi_report_id))
    db.session.delete(rpt)
    db.session.commit()
    flash('Deleted report', 'info')
    return redirect(url_for('analytics.route_hsireports'))

@bp_hsireports.route('/upload', methods=['POST'])
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
    if signature:
        try:
            info = _pkcs7_signature_info(signature, check_rc=False)
        except IOError as e:
            return _json_error('Signature invalid: %s' % str(e))
        if 'serial' not in info:
            return _json_error('Signature invalid, no signature')

    # parse JSON data
    try:
        item = json.loads(payload)
    except ValueError as e:
        return _json_error('No JSON object could be decoded: ' + str(e))

    # check we got enough data
    for key in ['ReportVersion', 'MachineId', 'Metadata']:
        if not key in item:
            return _json_error('invalid data, expected %s' % key)
        if item[key] is None:
            return _json_error('missing data, expected %s' % key)

    # parse only this version
    if item['ReportVersion'] != 2:
        return _json_error('report version not supported')

    # add each firmware report
    machine_id = item['MachineId']
    if not _is_sha256(machine_id):
        return _json_error('MachineId invalid, expected SHA256')
    hsireports = item.get('HsiReports', [])
    sec_attrs = item.get('SecurityAttributes', [])
    if not hsireports and not sec_attrs:
        return _json_error('no hsireports included')
    metadata = item['Metadata']
    if not metadata:
        return _json_error('no metadata included')

    if sec_attrs:

        # required metadata for this report type
        for key in ['HostProduct', 'HostFamily', 'HostVendor', 'HostSku']:
            if not key in metadata:
                return _json_error('invalid data, expected %s' % key)
            if metadata[key] is None:
                return _json_error('missing data, expected %s' % key)

        # check attrs
        for sec_attr in sec_attrs:
            for key in ['AppstreamId', 'HsiResult']:
                if not key in sec_attr:
                    return _json_error('invalid data, expected %s' % key)
                if sec_attr[key] is None:
                    return _json_error('missing data, expected %s' % key)

        # update any old report
        rpt = db.session.query(HsiReport)\
                        .filter(HsiReport.machine_id == machine_id).first()
        if rpt:
            db.session.delete(rpt)

        # construct a single string
        distro = '{} {} ({})'.format(metadata.get('DistroId', 'Unknown'),
                                     metadata.get('DistroVersion', 'Unknown'),
                                     metadata.get('DistroVariant', 'Unknown'))

        # save a new report in the database
        host_security_parts = metadata['HostSecurityId'].split(' ')
        rpt = HsiReport(payload=payload,          # in case we want to extract
                        signature=signature,      # if we want to match the user
                        machine_id=machine_id,
                        distro=distro,
                        kernel_cmdline=metadata.get('KernelCmdline'),
                        kernel_version=metadata.get('KernelVersion'),
                        host_product=metadata['HostProduct'],
                        host_vendor=metadata['HostVendor'],
                        host_family=metadata['HostFamily'],
                        host_sku=metadata['HostSku'],
                        host_security_id=host_security_parts[0],
                        host_security_version=host_security_parts[1][2:-1])
        for sec_attr in sec_attrs:
            flags = sec_attr.get('Flags', [])
            attr = HsiReportAttr(appstream_id=sec_attr['AppstreamId'],
                                 hsi_result=sec_attr['HsiResult'],
                                 is_runtime='runtime-issue' in flags,
                                 is_success='success' in flags,
                                 is_obsoleted='obsoleted' in flags)
            rpt.attrs.append(attr)
        db.session.add(rpt)

    # all done
    db.session.commit()
    return _json_success()
