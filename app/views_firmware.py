#!/usr/bin/python2
# -*- coding: utf-8 -*-
#
# Copyright (C) 2017-2018 Richard Hughes <richard@hughsie.com>
# Licensed under the GNU General Public License Version 2

import os
import datetime
import shutil

from flask import request, url_for, redirect, render_template, flash, g
from flask_login import login_required
from sqlalchemy.orm import joinedload

from gi.repository import AppStreamGlib
from gi.repository import GLib

from app import app, db
from .dbutils import _execute_count_star

from .models import Firmware, Report, Client, FirmwareEvent, FirmwareLimit, Remote, Vendor
from .util import _error_internal, _error_permission_denied
from .util import _get_chart_labels_months, _get_chart_labels_days

@app.route('/lvfs/firmware')
@login_required
def firmware(show_all=False):
    """
    Show all previsouly uploaded firmware for this user.
    """

    # group by the firmware name
    names = {}
    for fw in db.session.query(Firmware).\
                order_by(Firmware.timestamp.desc()).all():
        if not fw.check_acl('@view'):
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
            key = fw.remote.name + fw.mds[0].appstream_id
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

    # security check
    for md in fw.mds:
        if not md.check_acl('@modify-updateinfo'):
            return _error_permission_denied('Insufficient permissions to modify firmware')

    # set new metadata values
    for md in fw.mds:
        if 'urgency' in request.form:
            md.release_urgency = request.form['urgency']
        if 'description' in request.form:
            txt = request.form['description']
            if txt:
                if txt.find('<p>') == -1 and txt.find('<li>') == -1:
                    txt = AppStreamGlib.markup_import(txt, AppStreamGlib.MarkupConvertFormat.SIMPLE)
                try:
                    AppStreamGlib.markup_validate(txt)
                except GLib.Error as e: # pylint: disable=catching-non-exception
                    return _error_internal("Failed to parse %s: %s" % (txt, str(e)))
            md.release_description = unicode(txt)

    # modify
    db.session.commit()
    flash('Update text updated', 'info')
    return redirect(url_for('.firmware_show', firmware_id=firmware_id))

@app.route('/lvfs/firmware/<int:firmware_id>/undelete')
@login_required
def firmware_undelete(firmware_id):
    """ Undelete a firmware entry and also restore the file from disk """

    # check firmware exists in database
    fw = db.session.query(Firmware).filter(Firmware.firmware_id == firmware_id).first()
    if not fw:
        return _error_internal("No firmware file with ID %s exists" % firmware_id)

    # security check
    if not fw.check_acl('@undelete'):
        return _error_permission_denied('Insufficient permissions to undelete firmware')

    # find private remote
    remote = db.session.query(Remote).filter(Remote.name == 'private').first()
    if not remote:
        return _error_internal('No private remote')

    # move file back to the right place
    path = os.path.join(app.config['RESTORE_DIR'], fw.filename)
    if os.path.exists(path):
        path_new = os.path.join(app.config['DOWNLOAD_DIR'], fw.filename)
        shutil.move(path, path_new)

    # put back to the private state
    fw.remote_id = remote.remote_id
    fw.events.append(FirmwareEvent(fw.remote_id, g.user.user_id))
    db.session.commit()

    flash('Firmware undeleted', 'info')
    return redirect(url_for('.firmware'))

def _firmware_delete(fw):

    # find private remote
    remote = db.session.query(Remote).filter(Remote.name == 'deleted').first()
    if not remote:
        return _error_internal('No deleted remote')

    # move file so it's no longer downloadable
    path = os.path.join(app.config['DOWNLOAD_DIR'], fw.filename)
    if os.path.exists(path):
        path_new = os.path.join(app.config['RESTORE_DIR'], fw.filename)
        shutil.move(path, path_new)

    # generate next cron run
    fw.remote.is_dirty = True

    # mark as invalid
    fw.remote_id = remote.remote_id
    fw.events.append(FirmwareEvent(fw.remote_id, g.user.user_id))

@app.route('/lvfs/firmware/<int:firmware_id>/delete')
@login_required
def firmware_delete(firmware_id):
    """ Delete a firmware entry and also delete the file from disk """

    # check firmware exists in database
    fw = db.session.query(Firmware).filter(Firmware.firmware_id == firmware_id).first()
    if not fw:
        return _error_internal("No firmware file with ID %s exists" % firmware_id)

    # security check
    if not fw.check_acl('@delete'):
        return _error_permission_denied('Insufficient permissions to delete firmware')

    # delete firmware
    _firmware_delete(fw)
    db.session.commit()

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

    # security check
    if not fw.check_acl('@promote-' + target):
        return _error_permission_denied("No QA access to %s" % fw.firmware_id)

    # vendor has to fix the problems first
    if target in ['stable', 'testing'] and fw.problems:
        probs = ','.join(fw.problems)
        flash('Firmware has problems that must be fixed first: %s' % probs, 'warning')
        return redirect(url_for('.firmware_show', firmware_id=firmware_id))

    # set new remote
    if target == 'embargo':
        remote = fw.vendor.remote
    else:
        remote = db.session.query(Remote).filter(Remote.name == target).first()
    if not remote:
        return _error_internal('No remote for target %s' % target)

    # same as before
    if fw.remote.remote_id == remote.remote_id:
        flash('Cannot move firmware: Firmware already in that target', 'info')
        return redirect(url_for('.firmware_show', firmware_id=firmware_id))

    # invalidate both the remote it came from and the one it's going to
    remote.is_dirty = True
    fw.remote.is_dirty = True

    # also dirty any ODM remote if uploading on behalf of an OEM
    if target == 'embargo' and fw.vendor != fw.user.vendor:
        fw.user.vendor.remote.is_dirty = True

    # all okay
    fw.remote_id = remote.remote_id
    fw.events.append(FirmwareEvent(fw.remote_id, g.user.user_id))
    db.session.commit()
    flash('Moved firmware', 'info')

    return redirect(url_for('.firmware_show', firmware_id=firmware_id))

@app.route('/lvfs/firmware/<int:firmware_id>/components')
@login_required
def firmware_components(firmware_id):

    # get details about the firmware
    fw = db.session.query(Firmware).\
            filter(Firmware.firmware_id == firmware_id).first()
    if not fw:
        return _error_internal('No firmware matched!')

    # security check
    if not fw.check_acl('@view'):
        return _error_permission_denied('Insufficient permissions to view components')

    return render_template('firmware-components.html', fw=fw)

@app.route('/lvfs/firmware/<int:firmware_id>/limits')
@login_required
def firmware_limits(firmware_id):

    # get details about the firmware
    fw = db.session.query(Firmware).\
            filter(Firmware.firmware_id == firmware_id).first()
    if not fw:
        return _error_internal('No firmware matched!')

    # security check
    if not fw.check_acl('@view'):
        return _error_permission_denied('Insufficient permissions to view limits')

    return render_template('firmware-limits.html', fw=fw)

@app.route('/lvfs/firmware/limit/<int:firmware_limit_id>/delete')
@login_required
def firmware_limit_delete(firmware_limit_id):

    # get details about the firmware
    fl = db.session.query(FirmwareLimit).\
            filter(FirmwareLimit.firmware_limit_id == firmware_limit_id).first()
    if not fl:
        return _error_internal('No firmware limit matched!')

    # security check
    if not fl.fw.check_acl('delete-limit'):
        return _error_permission_denied('Insufficient permissions to delete limits')

    firmware_id = fl.firmware_id
    db.session.delete(fl)
    db.session.commit()
    flash('Deleted limit', 'info')
    return redirect(url_for('.firmware_limits', firmware_id=firmware_id))

@app.route('/lvfs/firmware/limit/add', methods=['POST'])
@login_required
def firmware_limit_add():

    # get details about the firmware
    fw = db.session.query(Firmware).\
            filter(Firmware.firmware_id == request.form['firmware_id']).first()
    if not fw:
        return _error_internal('No firmware matched!')

    # security check
    if not fw.check_acl('@add-limit'):
        return _error_permission_denied('Unable to add restriction')

    # ensure has enough data
    for key in ['value', 'firmware_id']:
        if key not in request.form:
            return _error_internal('No %s form data found!', key)

    # add restriction
    fl = FirmwareLimit(firmware_id=request.form['firmware_id'],
                       value=request.form['value'],
                       user_agent_glob=request.form['user_agent_glob'],
                       response=request.form['response'])
    db.session.add(fl)
    db.session.commit()
    flash('Added limit', 'info')
    return redirect(url_for('.firmware_limits', firmware_id=fl.firmware_id))


@app.route('/lvfs/firmware/<int:firmware_id>/affiliation')
@login_required
def firmware_affiliation(firmware_id):

    # get details about the firmware
    fw = db.session.query(Firmware).\
            filter(Firmware.firmware_id == firmware_id).first()
    if not fw:
        return _error_internal('No firmware matched!')

    # security check
    if not fw.check_acl('@modify-affiliation'):
        return _error_permission_denied('Insufficient permissions to modify affiliations')

    # add other vendors
    if g.user.check_acl('@admin'):
        vendors = []
        for v in db.session.query(Vendor).order_by(Vendor.display_name).all():
            if v.is_account_holder != 'yes':
                continue
            vendors.append(v)
    else:
        vendors = [g.user.vendor]
        for aff in fw.vendor.affiliations_for:
            vendors.append(aff.vendor)

    return render_template('firmware-affiliation.html', fw=fw, vendors=vendors)

@app.route('/lvfs/firmware/<int:firmware_id>/affiliation/change', methods=['POST'])
@login_required
def firmware_affiliation_change(firmware_id):
    """ Changes the assigned vendor ID for the firmware """

    # change the vendor
    if 'vendor_id' not in request.form:
        return _error_internal('No vendor ID specified')

    # find firmware
    fw = db.session.query(Firmware).filter(Firmware.firmware_id == firmware_id).first()
    if not fw:
        return _error_internal("No firmware %s" % firmware_id)

    # security check
    if not fw.check_acl('@modify-affiliation'):
        return _error_permission_denied('Insufficient permissions to change affiliation')

    vendor_id = int(request.form['vendor_id'])
    if vendor_id == fw.vendor_id:
        flash('No affiliation change required', 'info')
        return redirect(url_for('.firmware_affiliation', firmware_id=fw.firmware_id))
    if not g.user.is_admin and not g.user.vendor.is_affiliate_for(vendor_id):
        return _error_permission_denied('Insufficient permissions to change affiliation to %u' % vendor_id)
    old_vendor = fw.vendor
    fw.vendor_id = vendor_id
    db.session.commit()

    # do we need to regenerate remotes?
    if fw.remote.name.startswith('embargo'):
        fw.vendor.remote.is_dirty = True
        fw.user.vendor.remote.is_dirty = True
        old_vendor.remote.is_dirty = True
        fw.remote_id = fw.vendor.remote.remote_id
        fw.events.append(FirmwareEvent(fw.remote_id, g.user.user_id))
        db.session.commit()

    flash('Changed firmware vendor', 'info')
    return redirect(url_for('.firmware_show', firmware_id=fw.firmware_id))

@app.route('/lvfs/firmware/<int:firmware_id>/problems')
@login_required
def firmware_problems(firmware_id):

    # get details about the firmware
    fw = db.session.query(Firmware).\
            filter(Firmware.firmware_id == firmware_id).first()
    if not fw:
        return _error_internal('No firmware matched!')

    # security check
    if not fw.check_acl('@view'):
        return _error_permission_denied('Insufficient permissions to view components')

    return render_template('firmware-problems.html', fw=fw)

@app.route('/lvfs/firmware/<int:firmware_id>/history')
@login_required
def firmware_history(firmware_id):

    # get details about the firmware
    fw = db.session.query(Firmware).\
            filter(Firmware.firmware_id == firmware_id).first()
    if not fw:
        return _error_internal('No firmware matched!')

    # security check
    if not fw.check_acl('@view'):
        return _error_permission_denied('Insufficient permissions to view components')

    return render_template('firmware-history.html', fw=fw)

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

    # security check
    if not fw.check_acl('@view'):
        return _error_permission_denied('Insufficient permissions to view firmware')

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

    return render_template('firmware-details.html',
                           fw=fw,
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

    # get details about the firmware
    fw = db.session.query(Firmware).filter(Firmware.firmware_id == firmware_id).first()
    if not fw:
        return _error_internal('No firmware matched!')

    # security check
    if not fw.check_acl('@view-analytics'):
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

    # get details about the firmware
    fw = db.session.query(Firmware).filter(Firmware.firmware_id == firmware_id).first()
    if not fw:
        return _error_internal('No firmware matched!')

    # security check
    if not fw.check_acl('@view-analytics'):
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

    # get reports about the firmware
    fw = db.session.query(Firmware).filter(Firmware.firmware_id == firmware_id).first()
    if not fw:
        return _error_internal('No firmware matched!')

    # security check
    if not fw.check_acl('@view-analytics'):
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

    # get details about the firmware
    fw = db.session.query(Firmware).filter(Firmware.firmware_id == firmware_id).first()
    if not fw:
        return _error_internal('No firmware matched!')

    # security check
    if not fw.check_acl('@view-analytics'):
        return _error_permission_denied('Insufficient permissions to view analytics')

    data_fw = _get_stats_for_fw(30, 1, fw)
    return render_template('firmware-analytics-month.html',
                           fw=fw,
                           graph_labels=_get_chart_labels_days()[::-1],
                           graph_data=data_fw[::-1])
