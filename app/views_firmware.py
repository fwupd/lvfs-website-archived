#!/usr/bin/python2
# -*- coding: utf-8 -*-
#
# Copyright (C) 2017 Richard Hughes <richard@hughsie.com>
# Licensed under the GNU General Public License Version 2

import os
import json

from flask import request, url_for, redirect, render_template, flash, Response, g
from flask_login import login_required

from gi.repository import AppStreamGlib
from gi.repository import GLib

from app import app, db

from .db import CursorError
from .hash import _qa_hash
from .metadata import _metadata_update_group, _metadata_update_targets
from .models import FirmwareRequirement, UserCapability
from .util import _event_log, _error_internal, _error_permission_denied, _get_chart_labels_months, _get_chart_labels_days, _validate_guid

def _get_split_names_for_firmware(fw):
    names = []
    for md in fw.mds:
        name_safe = md.name.replace(' System Update', '')
        name_split = name_safe.split('/')
        all_substrings_long_enough = True
        for name in name_split:
            if len(name) < 8:
                all_substrings_long_enough = False
                break
        if all_substrings_long_enough:
            for name in name_split:
                names.append(name)
        else:
            names.append(name_safe)
    return sorted(names)

@app.route('/lvfs/firmware')
@login_required
def firmware(show_all=False):
    """
    Show all previsouly uploaded firmware for this user.
    """

    # check is valid
    if not g.user.check_capability(UserCapability.User):
        return _error_permission_denied('Not a valid user')

    # group by the firmware name
    names = {}
    for item in db.firmware.get_all():
        # admin can see everything
        if g.user.username != 'admin':
            if item.group_id != g.user.group_id:
                continue
        if len(item.mds) == 0:
            continue
        name = item.mds[0].developer_name + ' ' + item.mds[0].name
        if not name in names:
            names[name] = []
        names[name].append(item)

    # only show one version in each state
    for name in sorted(names):
        targets_seen = {}
        for item in names[name]:
            if len(item.mds) == 0:
                continue
            key = item.target + item.mds[0].cid
            if key in targets_seen:
                item.is_newest_in_state = False
            else:
                item.is_newest_in_state = True
                targets_seen[key] = item

    return render_template('firmware.html',
                           fw_by_name=names,
                           names_sorted=sorted(names),
                           show_all=show_all)

@app.route('/lvfs/firmware_all')
def firmware_all():
    return firmware(True)

@app.route('/lvfs/firmware/<firmware_id>/delete')
def firmware_delete(firmware_id):
    """ Confirms deletion of firmware """
    return render_template('firmware-delete.html', firmware_id=firmware_id), 406

@app.route('/lvfs/firmware/<firmware_id>/modify', methods=['GET', 'POST'])
@login_required
def firmware_modify(firmware_id):
    """ Modifies the update urgency and release notes for the update """

    if request.method != 'POST':
        return redirect(url_for('.firmware'))

    # find firmware
    fwobj = db.firmware.get_item(firmware_id)
    if not fwobj:
        return _error_internal("No firmware %s" % firmware_id)

    # set new metadata values
    for md in fwobj.mds:
        if 'urgency' in request.form:
            md.release_urgency = request.form['urgency']
        if 'description' in request.form:
            txt = request.form['description']
            if txt.find('<p>') == -1:
                txt = AppStreamGlib.markup_import(txt, AppStreamGlib.MarkupConvertFormat.SIMPLE)
            try:
                AppStreamGlib.markup_validate(txt)
            except GLib.Error as e:
                return _error_internal("Failed to parse %s: %s" % (txt, str(e)))
            md.release_description = txt

    # modify
    db.firmware.update(fwobj)

    # log
    _event_log('Changed update description on %s' % firmware_id)

    return redirect(url_for('.firmware_show', firmware_id=firmware_id))

@app.route('/lvfs/firmware/<firmware_id>/modify_requirements', methods=['GET', 'POST'])
@login_required
def firmware_modify_requirements(firmware_id):
    """ Modifies the update urgency and release notes for the update """

    if request.method != 'POST':
        return redirect(url_for('.firmware'))

    # find firmware
    fwobj = db.firmware.get_item(firmware_id)
    if not fwobj:
        return _error_internal("No firmware %s" % firmware_id)

    # set new metadata values
    for md in fwobj.mds:
        if 'requirements' in request.form:
            req_txt = request.form['requirements']
            req_txt = req_txt.replace('\n', ',')
            req_txt = req_txt.replace('\r', '')
            md.requirements = []
            for req in req_txt.split(','):
                req = req.strip()
                if len(req) == 0:
                    continue
                if len(req.split('/')) != 4:
                    return _error_internal("Failed to parse %s" % req)
                fwreq = FirmwareRequirement(req[0], req[1], req[2], req[3])
                md.requirements.append(fwreq)

    # modify
    db.firmware.update(fwobj)

    # log
    _event_log('Changed requirements on %s' % firmware_id)

    return redirect(url_for('.firmware_show', firmware_id=firmware_id))

@app.route('/lvfs/firmware/<firmware_id>/delete_force')
@login_required
def firmware_delete_force(firmware_id):
    """ Delete a firmware entry and also delete the file from disk """

    # check firmware exists in database
    item = db.firmware.get_item(firmware_id)
    if not item:
        return _error_internal("No firmware file with hash %s exists" % firmware_id)
    if not g.user.check_group_id(item.group_id):
        return _error_permission_denied("No QA access to %s" % firmware_id)

    # only QA users can delete once the firmware has gone stable
    if not g.user.is_qa and item.target == 'stable':
        return _error_permission_denied('Unable to delete stable firmware as not QA')

    # delete id from database
    db.firmware.remove(firmware_id)

    # delete file
    path = os.path.join(app.config['DOWNLOAD_DIR'], item.filename)
    if os.path.exists(path):
        os.remove(path)

    # update everything
    _metadata_update_group(item.group_id)
    if item.target == 'stable':
        _metadata_update_targets(targets=['stable', 'testing'])
    elif item.target == 'testing':
        _metadata_update_targets(targets=['testing'])

    _event_log("Deleted firmware %s" % firmware_id)
    return redirect(url_for('.firmware'))

@app.route('/lvfs/firmware/<firmware_id>/promote/<target>')
@login_required
def firmware_promote(firmware_id, target):
    """
    Promote or demote a firmware file from one target to another,
    for example from testing to stable, or stable to testing.
     """

    # check is QA
    if not g.user.check_capability(UserCapability.QA):
        return _error_permission_denied('Unable to promote as not QA')

    # check valid
    if target not in ['stable', 'testing', 'private', 'embargo']:
        return _error_internal("Target %s invalid" % target)

    # check firmware exists in database
    item = db.firmware.get_item(firmware_id)
    if not item:
        return _error_internal('No firmware matched!')
    if not g.user.check_group_id(item.group_id):
        return _error_permission_denied("No QA access to %s" % firmware_id)
    db.firmware.set_target(firmware_id, target)
    # set correct response code
    _event_log("Moved firmware %s to %s" % (firmware_id, target))

    # update everything
    _metadata_update_group(item.group_id)
    targets = []
    if target == 'stable' or item.target == 'stable':
        targets.append('stable')
    if target == 'testing' or item.target == 'testing':
        targets.append('testing')
    if len(targets) > 0:
        _metadata_update_targets(targets)
    return redirect(url_for('.firmware_show', firmware_id=firmware_id))

@app.route('/lvfs/firmware/<firmware_id>')
@login_required
def firmware_show(firmware_id):
    """ Show firmware information """

    # get details about the firmware
    item = db.firmware.get_item(firmware_id)
    if not item:
        return _error_internal('No firmware matched!')

    # we can only view our own firmware, unless admin
    if not g.user.check_group_id(item.group_id):
        return _error_permission_denied('Unable to view other vendor firmware')

    embargo_url = '/downloads/firmware-%s.xml.gz' % _qa_hash(item.group_id)

    # get the reports for this firmware
    reports_success = 0
    reports_failure = 0
    reports = db.reports.get_all_for_firmware_id(firmware_id, limit=0)
    for r in reports:
        if r.state == 2:
            reports_success += 1
        elif r.state == 3:
            reports_failure += 1

    cnt_fn = db.clients.get_firmware_count_filename(item.filename)
    return render_template('firmware-details.html',
                           fw=item,
                           qa_capability=g.user.is_qa,
                           orig_filename='-'.join(item.filename.split('-')[1:]),
                           embargo_url=embargo_url,
                           group_id=item.group_id,
                           cnt_fn=cnt_fn,
                           reports_success=reports_success,
                           reports_failure=reports_failure,
                           firmware_id=firmware_id)

@app.route('/lvfs/firmware/<firmware_id>/analytics/year')
@login_required
def firmware_analytics_year(firmware_id):
    """ Show firmware analytics information """

    # get details about the firmware
    item = db.firmware.get_item(firmware_id)
    if not item:
        return _error_internal('No firmware matched!')

    # we can only view our own firmware, unless admin
    if not g.user.check_group_id(item.group_id):
        return _error_permission_denied('Unable to view other vendor firmware')

    data_fw = db.clients.get_stats_for_fn(12, 30, item.filename)
    return render_template('firmware-analytics-year.html',
                           fw=item,
                           firmware_id=firmware_id,
                           graph_labels=_get_chart_labels_months()[::-1],
                           graph_data=data_fw[::-1])

@app.route('/lvfs/firmware/<firmware_id>/analytics')
@app.route('/lvfs/firmware/<firmware_id>/analytics/clients')
@login_required
def firmware_analytics_clients(firmware_id):
    """ Show firmware clients information """

    # get details about the firmware
    item = db.firmware.get_item(firmware_id)
    if not item:
        return _error_internal('No firmware matched!')

    # we can only view our own firmware, unless admin
    if not g.user.check_group_id(item.group_id):
        return _error_permission_denied('Unable to view other vendor firmware')
    clients = db.clients.get_all_for_filename(item.filename)
    return render_template('firmware-analytics-clients.html',
                           fw=item,
                           firmware_id=firmware_id,
                           clients=clients)

@app.route('/lvfs/firmware/<firmware_id>/analytics/reports')
@app.route('/lvfs/firmware/<firmware_id>/analytics/reports/<int:state>')
@login_required
def firmware_analytics_reports(firmware_id, state=None):
    """ Show firmware clients information """

    # get reports about the firmware
    item = db.firmware.get_item(firmware_id)
    if not item:
        return _error_internal('No firmware matched!')

    # we can only view our own firmware, unless admin
    if not g.user.check_group_id(item.group_id):
        return _error_permission_denied('Unable to view other vendor firmware')
    reports = db.reports.get_all_for_firmware_id(firmware_id)
    reports_filtered = []
    for r in reports:
        if state and r.state != state:
            continue
        reports_filtered.append(r)
    return render_template('firmware-analytics-reports.html',
                           fw=item,
                           state=state,
                           firmware_id=firmware_id,
                           reports=reports_filtered)

@app.route('/lvfs/firmware/<firmware_id>/analytics/month')
@login_required
def firmware_analytics_month(firmware_id):
    """ Show firmware analytics information """

    # get details about the firmware
    item = db.firmware.get_item(firmware_id)
    if not item:
        return _error_internal('No firmware matched!')

    # we can only view our own firmware, unless admin
    if not g.user.check_group_id(item.group_id):
        return _error_permission_denied('Unable to view other vendor firmware')

    data_fw = db.clients.get_stats_for_fn(30, 1, item.filename)
    return render_template('firmware-analytics-month.html',
                           fw=item,
                           firmware_id=firmware_id,
                           graph_labels=_get_chart_labels_days()[::-1],
                           graph_data=data_fw[::-1])

# get the right component
def _item_filter_by_cid(item, cid):
    for md in item.mds:
        if md.cid == cid:
            return md

@app.route('/lvfs/firmware/<firmware_id>/component/<cid>')
@app.route('/lvfs/firmware/<firmware_id>/component/<cid>/<page>')
@login_required
def firmware_component_show(firmware_id, cid, page='overview'):
    """ Show firmware component information """

    # get firmware component
    fwobj = db.firmware.get_item(firmware_id)
    if not fwobj:
        return _error_internal('No firmware matched!')
    md = _item_filter_by_cid(fwobj, cid)
    if not md:
        return _error_internal('No component matched!')

    # we can only view our own firmware, unless admin
    if not g.user.check_group_id(fwobj.group_id):
        return _error_permission_denied('Unable to view other vendor firmware')

    return render_template('firmware-md-' + page + '.html',
                           md=md,
                           fw=fwobj,
                           firmware_id=firmware_id)

@app.route('/lvfs/telemetry/repair')
@login_required
def telemetry_repair():
    if not g.user.check_capability(UserCapability.Admin):
        return _error_permission_denied('Not admin user')
    for fw in db.firmware.get_all():
        cnt = db.clients.get_firmware_count_filename(fw.filename)
        db.firmware.set_download_count(fw.firmware_id, cnt)
    return redirect(url_for('.telemetry'))

@app.route('/lvfs/telemetry/<int:age>/<sort_key>/<sort_direction>')
@app.route('/lvfs/telemetry/<int:age>/<sort_key>')
@app.route('/lvfs/telemetry/<int:age>')
@app.route('/lvfs/telemetry')
@login_required
def telemetry(age=0, sort_key='downloads', sort_direction='up'):
    """ Show firmware component information """

    # only QA users can view this data
    if not g.user.check_capability(UserCapability.QA):
        return _error_permission_denied('Unable to view telemetry as not QA')

    # get data
    total_downloads = 0
    total_success = 0
    total_failed = 0
    show_duplicate_warning = False
    firmware = []
    for fw in db.firmware.get_all():

        # not allowed to view
        if not g.user.check_capability(UserCapability.Admin) and fw.group_id != g.user.group_id:
            continue
        if len(fw.mds) == 0:
            continue
        if fw.target == 'private' or fw.target == 'embargo':
            continue

        # reports
        if age == 0:
            cnt_download = fw.download_cnt
        else:
            cnt_download = db.clients.get_firmware_count_filename(fw.filename, age)
        cnt_success = 0
        cnt_failed = 0
        rpts = db.reports.get_all_for_firmware_id(fw.firmware_id, age=age, limit=0)
        for rpt in rpts:
            if rpt.state == 2:
                cnt_success += 1
            if rpt.state == 3:
                cnt_failed += 1
        total_success += cnt_success
        total_failed += cnt_failed
        total_downloads += cnt_download

        # add items
        res = {}
        res['downloads'] = cnt_download
        res['success'] = cnt_success
        res['failed'] = cnt_failed
        res['names'] = _get_split_names_for_firmware(fw)
        res['version'] = fw.version_display
        if not res['version']:
            res['version'] = fw.mds[0].version
        res['nameversion'] = res['names'][0] + ' ' + res['version']
        res['firmware_id'] = fw.firmware_id
        res['target'] = fw.target
        res['duplicate'] = len(fw.mds)
        firmware.append(res)

        # show the user a warning
        if len(fw.mds) > 1:
            show_duplicate_warning = True

    if sort_direction == 'down':
        firmware.sort(key=lambda x: x['downloads'])
        firmware.sort(key=lambda x: x[sort_key])
    else:
        firmware.sort(key=lambda x: x['downloads'], reverse=True)
        firmware.sort(key=lambda x: x[sort_key], reverse=True)
    return render_template('telemetry.html',
                           age=age,
                           sort_key=sort_key,
                           sort_direction=sort_direction,
                           firmware=firmware,
                           group_id=g.user.group_id,
                           show_duplicate_warning=show_duplicate_warning,
                           total_failed=total_failed,
                           total_downloads=total_downloads,
                           total_success=total_success)

@app.route('/lvfs/firmware/<firmware_id>/component/<cid>/requires/remove/hwid/<hwid>')
@login_required
def firmware_component_requires_remove_hwid(firmware_id, cid, hwid):

    # get firmware component
    fwobj = db.firmware.get_item(firmware_id)
    if not fwobj:
        return _error_internal('No firmware matched!')
    md = _item_filter_by_cid(fwobj, cid)
    if not md:
        return _error_internal('No component matched!')

    # we can only modify our own firmware, unless admin
    if not g.user.check_group_id(fwobj.group_id):
        return _error_permission_denied('Unable to modify other vendor firmware')

    # remove hwid
    fwreq = md.find_fwreq('hardware', hwid)
    md.requirements.remove(fwreq)

    # modify
    db.firmware.update(fwobj)

    # log
    _event_log('Removed HWID %s on %s' % (hwid, firmware_id))
    return redirect(url_for('.firmware_component_show',
                            firmware_id=firmware_id,
                            cid=cid,
                            page='requires'))

@app.route('/lvfs/firmware/<firmware_id>/component/<cid>/requires/add/hwid', methods=['POST'])
@login_required
def firmware_component_requires_add_hwid(firmware_id, cid):
    """ Modifies the update urgency and release notes for the update """

    # get firmware component
    fwobj = db.firmware.get_item(firmware_id)
    if not fwobj:
        return _error_internal('No firmware matched!')
    md = _item_filter_by_cid(fwobj, cid)
    if not md:
        return _error_internal('No component matched!')

    # we can only modify our own firmware, unless admin
    if not g.user.check_group_id(fwobj.group_id):
        return _error_permission_denied('Unable to modify other vendor firmware')

    # check we have data
    if 'hwid' not in request.form:
        return _error_internal('No hwid specified!')

    # add hwid
    hwid = request.form['hwid']
    fwreq = md.find_fwreq('hardware', hwid)
    if fwreq:
        flash('%s has already been added' % hwid, 'warning')
    elif not _validate_guid(hwid):
        flash('%s was not a valid GUID' % hwid, 'danger')
    else:
        fwreq = FirmwareRequirement('hardware', hwid)
        md.requirements.append(fwreq)
        db.firmware.update(fwobj)
        _event_log('Added HWID %s on %s' % (hwid, firmware_id))
    return redirect(url_for('.firmware_component_show',
                            firmware_id=firmware_id,
                            cid=cid,
                            page='requires'))

@app.route('/lvfs/firmware/<firmware_id>/component/<cid>/requires/set/<kind>/<value>', methods=['POST'])
@login_required
def firmware_component_requires_set(firmware_id, cid, kind, value):
    """ Modifies the update urgency and release notes for the update """

    # get firmware component
    fwobj = db.firmware.get_item(firmware_id)
    if not fwobj:
        return _error_internal('No firmware matched!')
    md = _item_filter_by_cid(fwobj, cid)
    if not md:
        return _error_internal('No component matched!')

    # we can only modify our own firmware, unless admin
    if not g.user.check_group_id(fwobj.group_id):
        return _error_permission_denied('Unable to modify other vendor firmware')

    # check we have data
    if 'compare' not in request.form:
        return _error_internal('No compare specified!')
    if 'version' not in request.form:
        return _error_internal('No version specified!')

    # modify hwid, removing or creating as required
    fwreq = md.find_fwreq(kind, value)
    if request.form['compare'] == '':
        if fwreq:
            md.requirements.remove(fwreq)
    else:
        if not fwreq:
            fwreq = FirmwareRequirement(kind, value)
            md.requirements.append(fwreq)
        fwreq.compare = request.form['compare']
        fwreq.version = request.form['version']
    db.firmware.update(fwobj)
    _event_log('Changed %s/%s requirement on %s' % (kind, value, firmware_id))
    return redirect(url_for('.firmware_component_show',
                            firmware_id=firmware_id,
                            cid=cid,
                            page='requires'))

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
        try:
            # try to find the firmware_id (which might not exist on this server)
            firmware_id = db.firmware.get_id_from_container_checksum(checksum)
            if not firmware_id:
                msgs.append('%s did not match any known firmware archive' % checksum)
                continue
            # remove any old report
            report_old = db.reports.find_by_id_checksum(machine_id, checksum)
            if report_old:
                msgs.append('%s replaces old report' % checksum)
                db.reports.remove_by_id(report_old.id)

            # copy shared metadata
            for key in metadata:
                if key in report_metadata:
                    continue
                report_metadata[key] = metadata[key]

            # save in the database
            json_raw = json.dumps(report, sort_keys=True,
                                  indent=2, separators=(',', ': '))
            db.reports.add(report['UpdateState'], machine_id, firmware_id, checksum, json_raw)
        except CursorError as e:
            return json_error(str(e))

    # get a message on one line
    if len(msgs) > 0:
        return json_success('\n'.join(msgs))

    # no messages to report
    return json_success()
