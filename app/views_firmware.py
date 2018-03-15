#!/usr/bin/python2
# -*- coding: utf-8 -*-
#
# Copyright (C) 2017-2018 Richard Hughes <richard@hughsie.com>
# Licensed under the GNU General Public License Version 2

import os
import datetime

from flask import request, url_for, redirect, render_template, flash, g
from flask_login import login_required
from sqlalchemy.orm import joinedload

from gi.repository import AppStreamGlib
from gi.repository import GLib

from app import app, db
from .dbutils import _execute_count_star

from .hash import _qa_hash
from .metadata import _metadata_update_group, _metadata_update_targets
from .models import UserCapability, Firmware, Report, Client, FirmwareEvent
from .util import _error_internal, _error_permission_denied
from .util import _get_chart_labels_months, _get_chart_labels_days

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
    for fw in db.session.query(Firmware).\
                order_by(Firmware.timestamp.desc()).all():
        if not g.user.check_for_firmware(fw, readonly=True):
            continue
        if len(fw.mds) == 0:
            continue
        name = fw.mds[0].developer_name + ' ' + fw.mds[0].name
        if not name in names:
            names[name] = []
        names[name].append(fw)

    # only show one version in each state
    for name in sorted(names):
        targets_seen = {}
        for fw in names[name]:
            if len(fw.mds) == 0:
                continue
            key = fw.target + fw.mds[0].appstream_id
            if key in targets_seen:
                fw.is_newest_in_state = False
            else:
                fw.is_newest_in_state = True
                targets_seen[key] = fw

    return render_template('firmware.html',
                           fw_by_name=names,
                           names_sorted=sorted(names),
                           show_all=show_all)

@app.route('/lvfs/firmware_all')
def firmware_all():
    return firmware(True)

@app.route('/lvfs/firmware/<int:firmware_id>/modify', methods=['GET', 'POST'])
@login_required
def firmware_modify(firmware_id):
    """ Modifies the update urgency and release notes for the update """

    if request.method != 'POST':
        return redirect(url_for('.firmware'))

    # find firmware
    fw = db.session.query(Firmware).filter(Firmware.firmware_id == firmware_id).first()
    if not fw:
        return _error_internal("No firmware %s" % firmware_id)
    if not g.user.check_for_firmware(fw):
        return _error_permission_denied('Insufficient permissions to modify firmware')

    # set new metadata values
    for md in fw.mds:
        if 'urgency' in request.form:
            md.release_urgency = request.form['urgency']
        if 'description' in request.form:
            txt = request.form['description']
            if txt:
                if txt.find('<p>') == -1:
                    txt = AppStreamGlib.markup_import(txt, AppStreamGlib.MarkupConvertFormat.SIMPLE)
                try:
                    AppStreamGlib.markup_validate(txt)
                except GLib.Error as e: # pylint: disable=catching-non-exception
                    return _error_internal("Failed to parse %s: %s" % (txt, str(e)))
            md.release_description = txt

    # modify
    db.session.commit()
    flash('Update text updated', 'info')
    return redirect(url_for('.firmware_show', firmware_id=firmware_id))

@app.route('/lvfs/firmware/<int:firmware_id>/delete')
@login_required
def firmware_delete(firmware_id):
    """ Delete a firmware entry and also delete the file from disk """

    # check firmware exists in database
    fw = db.session.query(Firmware).filter(Firmware.firmware_id == firmware_id).first()
    if not fw:
        return _error_internal("No firmware file with ID %s exists" % firmware_id)
    if not g.user.check_for_firmware(fw):
        return _error_permission_denied('Insufficient permissions to delete firmware')

    # only QA users can delete once the firmware has gone stable
    if not g.user.is_qa and fw.target == 'stable':
        return _error_permission_denied('Unable to delete stable firmware as not QA')

    # save so we can rebuild metadata after the firmware has been deleted
    group_id = fw.vendor.group_id

    # delete from database
    for md in fw.mds:
        for kw in md.keywords:
            db.session.delete(kw)
        for rq in md.requirements:
            db.session.delete(rq)
        for gu in md.guids:
            db.session.delete(gu)
        db.session.delete(md)
    for ev in fw.events:
        db.session.delete(ev)
    db.session.delete(fw)
    db.session.commit()

    # delete file
    path = os.path.join(app.config['DOWNLOAD_DIR'], fw.filename)
    if os.path.exists(path):
        os.remove(path)

    # update everything
    _metadata_update_group(group_id)
    if fw.target == 'stable':
        _metadata_update_targets(targets=['stable', 'testing'])
    elif fw.target == 'testing':
        _metadata_update_targets(targets=['testing'])

    flash('Firmware deleted', 'info')
    return redirect(url_for('.firmware'))

@app.route('/lvfs/firmware/<int:firmware_id>/promote/<target>')
@login_required
def firmware_promote(firmware_id, target):
    """
    Promote or demote a firmware file from one target to another,
    for example from testing to stable, or stable to testing.
     """

    # check valid
    if target not in ['stable', 'testing', 'private', 'embargo']:
        return _error_internal("Target %s invalid" % target)

    # check firmware exists in database
    fw = db.session.query(Firmware).filter(Firmware.firmware_id == firmware_id).first()
    if not fw:
        return _error_internal('No firmware matched!')
    if not g.user.check_for_firmware(fw):
        return _error_permission_denied("No QA access to %s" % fw.firmware_id)

    # same as before
    if fw.target == target:
        flash('Cannot move firmware: Firmware already in that target', 'info')
        return redirect(url_for('.firmware_show', firmware_id=firmware_id))

    # anything -> testing,stable = QA
    if target in ['testing', 'stable']:
        if not g.user.check_capability(UserCapability.QA):
            return _error_permission_denied('Unable to promote as not QA')

    # testing,stable -> anything = QA
    elif fw.target in ['testing', 'stable']:
        if not g.user.check_capability(UserCapability.QA):
            return _error_permission_denied('Unable to promote as not QA')

    # private,embargo -> embargo,private = User
    elif fw.target in ['private', 'embargo'] and target in ['private', 'embargo']:
        if not g.user.check_capability(UserCapability.User):
            return _error_permission_denied('Unable to promote as not User')

    # all okay
    fw.target = target
    fw.events.append(FirmwareEvent(target, g.user.user_id))
    db.session.commit()
    flash('Moved firmware', 'info')

    # update everything
    _metadata_update_group(fw.vendor.group_id)
    targets = []
    if target == 'stable' or fw.target == 'stable':
        targets.append('stable')
    if target == 'testing' or fw.target == 'testing':
        targets.append('testing')
    if len(targets) > 0:
        _metadata_update_targets(targets)
    return redirect(url_for('.firmware_show', firmware_id=firmware_id))

@app.route('/lvfs/firmware/<int:firmware_id>')
@login_required
def firmware_show(firmware_id):
    """ Show firmware information """

    # get details about the firmware
    fw = db.session.query(Firmware).\
            filter(Firmware.firmware_id == firmware_id).\
            options(joinedload('reports')).\
            first()
    if not fw:
        return _error_internal('No firmware matched!')

    # we can only view our own firmware, unless admin
    if not g.user.check_for_firmware(fw, readonly=True):
        return _error_permission_denied('Insufficient permissions to view firmware')

    embargo_url = '/downloads/firmware-%s.xml.gz' % _qa_hash(fw.vendor.group_id)

    # get the reports for this firmware
    reports_success = 0
    reports_failure = 0
    reports_issue = 0
    for r in fw.reports:
        if r.state == 2:
            reports_success += 1
        if r.state == 3:
            if r.issue_id:
                reports_issue += 1
            else:
                reports_failure += 1

    # does the firmware have any warnings
    vetos = []
    for md in fw.mds:
        if md.release_urgency == 'unknown':
            vetos.append('no-release-urgency')
        if not md.release_description or len(md.release_description) < 12:
            vetos.append('no-release-description')

    return render_template('firmware-details.html',
                           fw=fw,
                           orig_filename='-'.join(fw.filename.split('-')[1:]),
                           vetos=vetos,
                           embargo_url=embargo_url,
                           reports_success=reports_success,
                           reports_issue=reports_issue,
                           reports_failure=reports_failure)

def _get_stats_for_fw(size, interval, fw):
    """ Gets stats data """

    # yes, there's probably a way to do this in one query...
    data = []
    now = datetime.date.today()
    for i in range(size):
        start = now - datetime.timedelta((i * interval) + interval - 1)
        end = now - datetime.timedelta((i * interval) - 1)
        cnt = _execute_count_star(db.session.query(Client).\
                    filter(Client.firmware_id == fw.firmware_id).\
                    filter(Client.timestamp >= start).\
                    filter(Client.timestamp < end))
        data.append(int(cnt))
    return data

@app.route('/lvfs/firmware/<int:firmware_id>/analytics/year')
@login_required
def firmware_analytics_year(firmware_id):
    """ Show firmware analytics information """

    # only analysts can see this data
    if not g.user.check_capability(UserCapability.Analyst):
        return _error_permission_denied('Insufficient permissions to view analytics')

    # get details about the firmware
    fw = db.session.query(Firmware).filter(Firmware.firmware_id == firmware_id).first()
    if not fw:
        return _error_internal('No firmware matched!')

    # we can only view our own firmware, unless admin
    if not g.user.check_for_firmware(fw, readonly=True):
        return _error_permission_denied('Insufficient permissions to view analytics')

    data_fw = _get_stats_for_fw(12, 30, fw)
    return render_template('firmware-analytics-year.html',
                           fw=fw,
                           graph_labels=_get_chart_labels_months()[::-1],
                           graph_data=data_fw[::-1])

@app.route('/lvfs/firmware/<int:firmware_id>/analytics')
@app.route('/lvfs/firmware/<int:firmware_id>/analytics/clients')
@login_required
def firmware_analytics_clients(firmware_id):
    """ Show firmware clients information """

    # only analysts can see this data
    if not g.user.check_capability(UserCapability.Analyst):
        return _error_permission_denied('Insufficient permissions to view analytics')

    # get details about the firmware
    fw = db.session.query(Firmware).filter(Firmware.firmware_id == firmware_id).first()
    if not fw:
        return _error_internal('No firmware matched!')

    # we can only view our own firmware, unless admin
    if not g.user.check_for_firmware(fw, readonly=True):
        return _error_permission_denied('Insufficient permissions to view analytics')
    clients = db.session.query(Client).filter(Client.firmware_id == fw.firmware_id).\
                order_by(Client.id.desc()).limit(10).all()
    return render_template('firmware-analytics-clients.html',
                           fw=fw,
                           clients=clients)

@app.route('/lvfs/firmware/<int:firmware_id>/analytics/reports')
@app.route('/lvfs/firmware/<int:firmware_id>/analytics/reports/<int:state>')
@login_required
def firmware_analytics_reports(firmware_id, state=None):
    """ Show firmware clients information """

    # only analysts can see this data
    if not g.user.check_capability(UserCapability.Analyst):
        return _error_permission_denied('Insufficient permissions to view analytics')

    # get reports about the firmware
    fw = db.session.query(Firmware).filter(Firmware.firmware_id == firmware_id).first()
    if not fw:
        return _error_internal('No firmware matched!')

    # we can only view our own firmware, unless admin
    if not g.user.check_for_firmware(fw, readonly=True):
        return _error_permission_denied('Insufficient permissions to view analytics')
    if state:
        reports = db.session.query(Report).\
                    filter(Report.firmware_id == firmware_id).\
                    filter(Report.state == state).all()
    else:
        reports = db.session.query(Report).\
                    filter(Report.firmware_id == firmware_id).all()
    return render_template('firmware-analytics-reports.html',
                           fw=fw,
                           state=state,
                           reports=reports)

@app.route('/lvfs/firmware/<int:firmware_id>/analytics/month')
@login_required
def firmware_analytics_month(firmware_id):
    """ Show firmware analytics information """

    # only analysts can see this data
    if not g.user.check_capability(UserCapability.Analyst):
        return _error_permission_denied('Insufficient permissions to view analytics')

    # get details about the firmware
    fw = db.session.query(Firmware).filter(Firmware.firmware_id == firmware_id).first()
    if not fw:
        return _error_internal('No firmware matched!')

    # we can only view our own firmware, unless admin
    if not g.user.check_for_firmware(fw, readonly=True):
        return _error_permission_denied('Insufficient permissions to view analytics')

    data_fw = _get_stats_for_fw(30, 1, fw)
    return render_template('firmware-analytics-month.html',
                           fw=fw,
                           graph_labels=_get_chart_labels_days()[::-1],
                           graph_data=data_fw[::-1])
