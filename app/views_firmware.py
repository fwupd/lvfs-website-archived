#!/usr/bin/python3
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

from app import app, db

from .models import Firmware, Report, Client, FirmwareEvent, FirmwareLimit
from .models import Remote, Vendor, AnalyticFirmware, Component
from .models import ComponentShard, ComponentShardInfo, ComponentShardChecksum
from .models import _get_datestr_from_datetime
from .util import _error_internal, _error_permission_denied, _event_log
from .util import _get_chart_labels_months, _get_chart_labels_days, _get_shard_path

@app.route('/lvfs/firmware')
@app.route('/lvfs/firmware/state/<state>')
@login_required
def firmware(state=None):
    """
    Show all firmware uploaded by this user or vendor.
    """
    # pre-filter by user ID or vendor
    if g.user.is_analyst or g.user.is_qa:
        stmt = db.session.query(Firmware).\
                    filter(Firmware.vendor_id == g.user.vendor.vendor_id)
    else:
        stmt = db.session.query(Firmware).\
                    filter(Firmware.user_id == g.user.user_id)
    if not state:
        remote = None
    elif state == 'embargo':
        remote = g.user.vendor.remote
        stmt = stmt.filter(Firmware.remote_id == remote.remote_id)
    elif state in ['private', 'testing', 'stable', 'deleted']:
        remote = db.session.query(Remote).filter(Remote.name == state).one()
        stmt = stmt.filter(Firmware.remote_id == remote.remote_id)
    else:
        return _error_internal('no state of %s' % state)
    stmt = stmt.options(joinedload('tests'))
    fws = stmt.order_by(Firmware.timestamp.desc()).all()
    return render_template('firmware-search.html',
                           category='firmware',
                           state=state,
                           remote=remote,
                           fws=fws)

@app.route('/lvfs/firmware/new')
@app.route('/lvfs/firmware/new/<int:limit>')
def firmware_new(limit=50):

    # get a sorted list of vendors
    fwevs_public = db.session.query(FirmwareEvent).\
                join(Firmware).join(Remote).filter(Remote.is_public).\
                group_by(FirmwareEvent.firmware_id).\
                order_by(FirmwareEvent.timestamp.desc()).\
                options(joinedload(FirmwareEvent.fw)).\
                limit(limit).all()
    return render_template('firmware-new.html',
                           category='firmware',
                           fwevs=fwevs_public,
                           limit=limit)

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
    return redirect(url_for('.firmware_show', firmware_id=firmware_id))

def _firmware_delete(fw):

    # find private remote
    remote = db.session.query(Remote).filter(Remote.name == 'deleted').first()
    if not remote:
        _event_log('No deleted remote')
        return

    # move file so it's no longer downloadable
    path = os.path.join(app.config['DOWNLOAD_DIR'], fw.filename)
    if os.path.exists(path):
        path_new = os.path.join(app.config['RESTORE_DIR'], fw.filename)
        shutil.move(path, path_new)

    # generate next cron run
    fw.mark_dirty()

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

@app.route('/lvfs/firmware/<int:firmware_id>/nuke')
@login_required
def firmware_nuke(firmware_id):
    """ Delete a firmware entry and also delete the file from disk """

    # check firmware exists in database
    fw = db.session.query(Firmware).filter(Firmware.firmware_id == firmware_id).first()
    if not fw:
        return _error_internal("No firmware file with ID %s exists" % firmware_id)

    # firmware is not deleted yet
    if not fw.is_deleted:
        return _error_permission_denied('Cannot nuke file not yet deleted')

    # security check
    if not fw.check_acl('@nuke'):
        return _error_permission_denied('Insufficient permissions to nuke firmware')

    # really delete firmware
    path = os.path.join(app.config['RESTORE_DIR'], fw.filename)
    if os.path.exists(path):
        os.remove(path)

    # delete shard cache if they exist
    for md in fw.mds:
        for shard in md.shards:
            path = _get_shard_path(shard)
            if os.path.exists(path):
                os.remove(path)

    # generate next cron run
    fw.remote.is_dirty = True

    # delete everything we stored about the firmware
    db.session.delete(fw)

    # all done
    db.session.commit()

    flash('Firmware nuked', 'info')
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
        probs = []
        for problem in fw.problems:
            if problem.kind not in probs:
                probs.append(problem.kind)
        flash('Firmware has problems that must be fixed first: %s' % ','.join(probs), 'warning')
        return redirect(url_for('.firmware_problems', firmware_id=firmware_id))

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
        return redirect(url_for('.firmware_target', firmware_id=firmware_id))

    # invalidate both the remote it came from and the one it's going to
    remote.is_dirty = True
    fw.remote.is_dirty = True

    # invalidate the firmware as we're waiting for the metadata generation
    fw.mark_dirty()

    # also dirty any ODM remote if uploading on behalf of an OEM
    if target == 'embargo' and fw.vendor != fw.user.vendor:
        fw.user.vendor.remote.is_dirty = True

    # all okay
    fw.remote_id = remote.remote_id
    fw.events.append(FirmwareEvent(fw.remote_id, g.user.user_id))
    db.session.commit()
    flash('Moved firmware', 'info')

    return redirect(url_for('.firmware_target', firmware_id=firmware_id))

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

    return render_template('firmware-components.html',
                           category='firmware',
                           fw=fw)

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

    return render_template('firmware-limits.html',
                           category='firmware',
                           fw=fw)

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
    fl.fw.mark_dirty()
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
    fl.fw.mark_dirty()
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
            if not v.is_account_holder:
                continue
            vendors.append(v)
    else:
        vendors = [g.user.vendor]
        for aff in fw.vendor.affiliations_for:
            vendors.append(aff.vendor)

    return render_template('firmware-affiliation.html',
                           category='firmware',
                           fw=fw, vendors=vendors)

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
        fw.mark_dirty()
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

    return render_template('firmware-problems.html',
                           category='firmware',
                           fw=fw)

@app.route('/lvfs/firmware/<int:firmware_id>/target')
@login_required
def firmware_target(firmware_id):

    # get details about the firmware
    fw = db.session.query(Firmware).\
            filter(Firmware.firmware_id == firmware_id).first()
    if not fw:
        return _error_internal('No firmware matched!')

    # security check
    if not fw.check_acl('@view'):
        return _error_permission_denied('Insufficient permissions to view firmware')

    return render_template('firmware-target.html',
                           category='firmware',
                           fw=fw)

@app.route('/lvfs/firmware/<int:firmware_id>')
@login_required
def firmware_show(firmware_id):
    """ Show firmware information """

    # get details about the firmware
    fw = db.session.query(Firmware).\
            filter(Firmware.firmware_id == firmware_id).\
            first()
    if not fw:
        return _error_internal('No firmware matched!')

    # security check
    if not fw.check_acl('@view'):
        return _error_permission_denied('Insufficient permissions to view firmware')

    # get data for the last month or year
    graph_data = []
    graph_labels = None
    if fw.check_acl('@view-analytics'):
        if fw.timestamp > datetime.datetime.today() - datetime.timedelta(days=30):
            datestr = _get_datestr_from_datetime(datetime.date.today() - datetime.timedelta(days=31))
            data = db.session.query(AnalyticFirmware.cnt).\
                        filter(AnalyticFirmware.firmware_id == fw.firmware_id).\
                        filter(AnalyticFirmware.datestr > datestr).\
                        order_by(AnalyticFirmware.datestr.desc()).all()
            graph_data = [r[0] for r in data]
            graph_data = graph_data[::-1]
            graph_labels = _get_chart_labels_days(limit=len(data))[::-1]
        else:
            datestr = _get_datestr_from_datetime(datetime.date.today() - datetime.timedelta(days=360))
            data = db.session.query(AnalyticFirmware.cnt).\
                        filter(AnalyticFirmware.firmware_id == fw.firmware_id).\
                        filter(AnalyticFirmware.datestr > datestr).\
                        order_by(AnalyticFirmware.datestr.desc()).all()
            # put in month-sized buckets
            for _ in range(12):
                graph_data.append(0)
            cnt = 0
            for res in data:
                graph_data[int(cnt / 30)] += res[0]
                cnt += 1
            graph_data = graph_data[::-1]
            graph_labels = _get_chart_labels_months()[::-1]

    return render_template('firmware-details.html',
                           category='firmware',
                           fw=fw,
                           graph_data=graph_data,
                           graph_labels=graph_labels)

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
                           category='firmware',
                           fw=fw,
                           clients=clients)

@app.route('/lvfs/firmware/<int:firmware_id>/analytics/reports')
@app.route('/lvfs/firmware/<int:firmware_id>/analytics/reports/<int:state>')
@app.route('/lvfs/firmware/<int:firmware_id>/analytics/reports/<int:state>/<int:limit>')
@login_required
def firmware_analytics_reports(firmware_id, state=None, limit=100):
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
                    filter(Report.state == state).\
                    order_by(Report.timestamp.desc()).limit(limit).all()
    else:
        reports = db.session.query(Report).\
                    filter(Report.firmware_id == firmware_id).\
                    order_by(Report.timestamp.desc()).limit(limit).all()
    return render_template('firmware-analytics-reports.html',
                           category='firmware',
                           fw=fw,
                           state=state,
                           reports=reports)

@app.route('/lvfs/firmware/<int:firmware_id>/tests')
@login_required
def firmware_tests(firmware_id):

    # get details about the firmware
    fw = db.session.query(Firmware).\
            filter(Firmware.firmware_id == firmware_id).first()
    if not fw:
        return _error_internal('No firmware matched!')

    # security check
    if not fw.check_acl('@view'):
        return _error_permission_denied('Insufficient permissions to view firmwares')

    return render_template('firmware-tests.html',
                           category='firmware',
                           fw=fw)

@app.route('/lvfs/firmware/shard/search/<kind>/<value>')
@login_required
def firmware_shard_search(kind, value):
    """
    Show firmware with shards that match the value
    """

    if kind == 'guid':
        fws = db.session.query(Firmware).\
                    join(Component).\
                    join(ComponentShard).\
                    join(ComponentShardInfo).\
                    filter(ComponentShardInfo.guid == value).\
                    order_by(Firmware.firmware_id.desc()).all()
    elif kind == 'checksum':
        fws = db.session.query(Firmware).\
                    join(Component).\
                    join(ComponentShard).\
                    join(ComponentShardChecksum).\
                    filter(ComponentShardChecksum.value == value).\
                    order_by(Firmware.firmware_id.desc()).all()
    else:
        return _error_internal('Invalid kind!')
    if not fws:
        return _error_internal('No shards matched!')

    # filter by ACL
    fws_safe = []
    for fw in fws:
        if fw.check_acl('@view'):
            fws_safe.append(fw)

    return render_template('firmware-search.html',
                           category='firmware',
                           state='search',
                           remote=None,
                           fws=fws_safe)
