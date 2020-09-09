#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2017-2018 Richard Hughes <richard@hughsie.com>
#
# SPDX-License-Identifier: GPL-2.0+

import os
import datetime
import shutil

from flask import Blueprint, request, url_for, redirect, render_template, flash, g
from flask_login import login_required

from sqlalchemy.orm import joinedload

from celery.schedules import crontab

from lvfs import app, db, ploader, celery

from lvfs.emails import send_email
from lvfs.metadata.utils import _async_regenerate_remote
from lvfs.models import Firmware, Report, Client, FirmwareEvent, FirmwareLimit
from lvfs.models import Remote, Vendor, AnalyticFirmware, Component
from lvfs.models import ComponentShard, ComponentShardChecksum
from lvfs.models import _get_datestr_from_datetime
from lvfs.tests.utils import _async_test_run_for_firmware
from lvfs.util import _error_internal, admin_login_required
from lvfs.util import _get_chart_labels_months, _get_chart_labels_days, _get_shard_path
from .utils import _firmware_delete, _async_sign_fw, _async_autodelete

bp_firmware = Blueprint('firmware', __name__, template_folder='templates')

@celery.on_after_finalize.connect
def setup_periodic_tasks(sender, **_):
    sender.add_periodic_task(
        crontab(hour=2, minute=0),
        _async_autodelete.s(),
    )

@bp_firmware.route('/')
@bp_firmware.route('/state/<state>')
@login_required
def route_firmware(state=None):
    """
    Show all firmware uploaded by this user or vendor.
    """
    # pre-filter by user ID or vendor
    if g.user.check_acl('@analyst') or g.user.check_acl('@qa'):
        stmt = db.session.query(Firmware).\
                    filter((Firmware.vendor_id == g.user.vendor.vendor_id) | \
                           (Firmware.vendor_odm_id == g.user.vendor.vendor_id))
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

@bp_firmware.route('/user')
@login_required
def route_user():
    """
    Show all firmware uploaded by this user.
    """
    # pre-filter by user ID or vendor
    stmt = db.session.query(Firmware).filter(Firmware.user_id == g.user.user_id)
    stmt = stmt.options(joinedload('tests'))
    fws = stmt.order_by(Firmware.timestamp.desc()).all()
    return render_template('firmware-search.html',
                           category='firmware',
                           fws=fws)

@bp_firmware.route('/new')
@bp_firmware.route('/new/<int:limit>')
def route_new(limit=50):

    # get a sorted list of vendors
    fwevs_public = db.session.query(FirmwareEvent).\
                join(Firmware).join(Remote).filter(Remote.is_public).\
                distinct(FirmwareEvent.timestamp, FirmwareEvent.firmware_id).\
                order_by(FirmwareEvent.timestamp.desc()).\
                options(joinedload(FirmwareEvent.fw)).\
                limit(limit).all()
    return render_template('firmware-new.html',
                           category='firmware',
                           fwevs=fwevs_public,
                           limit=limit)

@bp_firmware.route('/<int:firmware_id>/undelete', methods=['POST'])
@login_required
def route_undelete(firmware_id):
    """ Undelete a firmware entry and also restore the file from disk """

    # check firmware exists in database
    fw = db.session.query(Firmware).filter(Firmware.firmware_id == firmware_id).first()
    if not fw:
        flash('No firmware {} exists'.format(firmware_id), 'danger')
        return redirect(url_for('firmware.route_firmware'))

    # security check
    if not fw.check_acl('@undelete'):
        flash('Permission denied: Insufficient permissions to undelete firmware', 'danger')
        return redirect(url_for('firmware.route_show', firmware_id=firmware_id))

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
    fw.events.append(FirmwareEvent(remote_id=fw.remote_id, user_id=g.user.user_id))
    db.session.commit()

    flash('Firmware undeleted', 'info')
    return redirect(url_for('firmware.route_show', firmware_id=firmware_id))

@bp_firmware.route('/<int:firmware_id>/delete', methods=['POST'])
@login_required
def route_delete(firmware_id):
    """ Delete a firmware entry and also delete the file from disk """

    # check firmware exists in database
    fw = db.session.query(Firmware).filter(Firmware.firmware_id == firmware_id).first()
    if not fw:
        flash('No firmware {} exists'.format(firmware_id), 'danger')
        return redirect(url_for('firmware.route_firmware'))

    # security check
    if not fw.check_acl('@delete'):
        flash('Permission denied: Insufficient permissions to delete firmware', 'danger')
        return redirect(url_for('firmware.route_show', firmware_id=firmware_id))

    # delete firmware
    _firmware_delete(fw)
    db.session.commit()

    flash('Firmware deleted', 'info')
    return redirect(url_for('firmware.route_firmware'))

@bp_firmware.route('/<int:firmware_id>/nuke', methods=['POST'])
@login_required
def route_nuke(firmware_id):
    """ Delete a firmware entry and also delete the file from disk """

    # check firmware exists in database
    fw = db.session.query(Firmware).filter(Firmware.firmware_id == firmware_id).first()
    if not fw:
        flash('No firmware {} exists'.format(firmware_id), 'danger')
        return redirect(url_for('firmware.route_firmware'))

    # firmware is not deleted yet
    if not fw.is_deleted:
        flash('Cannot nuke file not yet deleted', 'danger')
        return redirect(url_for('firmware.route_show', firmware_id=firmware_id))

    # security check
    if not fw.check_acl('@nuke'):
        flash('Permission denied: Insufficient permissions to nuke firmware', 'danger')
        return redirect(url_for('firmware.route_show', firmware_id=firmware_id))

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
    return redirect(url_for('firmware.route_firmware'))

@bp_firmware.route('/<int:firmware_id>/resign', methods=['POST'])
@login_required
@admin_login_required
def route_resign(firmware_id):
    """ Re-sign a firmware archive """

    # check firmware exists in database
    fw = db.session.query(Firmware).filter(Firmware.firmware_id == firmware_id).first()
    if not fw:
        flash('No firmware {} exists'.format(firmware_id), 'danger')
        return redirect(url_for('firmware.route_firmware'))

    # firmware is not signed yet
    if not g.user.check_acl('@admin') and not fw.signed_timestamp:
        flash('Cannot resign unsigned file', 'danger')
        return redirect(url_for('firmware.route_show', firmware_id=firmware_id))

    # asynchronously sign
    fw.signed_timestamp = None
    db.session.commit()
    _async_sign_fw.apply_async(args=(fw.firmware_id,), queue='firmware')

    flash('Firmware will be re-signed soon', 'info')
    return redirect(url_for('firmware.route_show', firmware_id=firmware_id))

@bp_firmware.route('/<int:firmware_id>/promote/<target>', methods=['POST'])
@login_required
def route_promote(firmware_id, target):
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
        flash('No firmware {} exists'.format(firmware_id), 'danger')
        return redirect(url_for('firmware.route_firmware'))

    # security check
    if not fw.check_acl('@promote-' + target):
        flash('Permission denied: No QA access to {}'.format(firmware_id), 'danger')
        return redirect(url_for('firmware.route_show', firmware_id=firmware_id))

    # vendor has to fix the problems first
    if target in ['stable', 'testing'] and fw.problems:
        probs = []
        for problem in fw.problems:
            if problem.kind not in probs:
                probs.append(problem.kind)
        flash('Firmware has problems that must be fixed first: %s' % ','.join(probs), 'warning')
        return redirect(url_for('firmware.route_problems', firmware_id=firmware_id))

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
        return redirect(url_for('firmware.route_target', firmware_id=firmware_id))

    # invalidate both the remote it "came from", the one it's "going to" and
    # also the remote of the vendor that uploaded it
    remote.is_dirty = True
    fw.remote.is_dirty = True
    fw.vendor_odm.remote.is_dirty = True

    # invalidate the firmware as we're waiting for the metadata generation
    fw.mark_dirty()
    db.session.commit()

    # asynchronously sign
    for r in set([remote, fw.remote, fw.vendor_odm.remote]):
        r.is_dirty = True
        _async_regenerate_remote.apply_async(args=(r.remote_id,), queue='metadata', countdown=1)

    # some tests only run when the firmware is in stable
    ploader.ensure_test_for_fw(fw)

    # sync everything we added
    db.session.commit()

    # asynchronously run
    _async_test_run_for_firmware.apply_async(args=(fw.firmware_id,))

    # also dirty any ODM remote if uploading on behalf of an OEM
    if target == 'embargo' and fw.vendor != fw.user.vendor:
        fw.user.vendor.remote.is_dirty = True

    # all okay
    fw.remote_id = remote.remote_id
    fw.events.append(FirmwareEvent(remote_id=fw.remote_id, user_id=g.user.user_id))
    db.session.commit()

    # send email
    for u in fw.get_possible_users_to_email:
        if u == g.user:
            continue
        if u.get_action('notify-promote'):
            send_email("[LVFS] Firmware has been promoted",
                       u.email_address,
                       render_template('email-firmware-promoted.txt',
                                       user=g.user, fw=fw))

    flash('Moved firmware', 'info')

    return redirect(url_for('firmware.route_target', firmware_id=firmware_id))

@bp_firmware.route('/<int:firmware_id>/components')
@login_required
def route_components(firmware_id):

    # get details about the firmware
    fw = db.session.query(Firmware).\
            filter(Firmware.firmware_id == firmware_id).first()
    if not fw:
        flash('No firmware {} exists'.format(firmware_id), 'danger')
        return redirect(url_for('firmware.route_firmware'))

    # security check
    if not fw.check_acl('@view'):
        flash('Permission denied: Insufficient permissions to view components', 'danger')
        return redirect(url_for('firmware.route_show', firmware_id=firmware_id))

    return render_template('firmware-components.html',
                           category='firmware',
                           fw=fw)

@bp_firmware.route('/<int:firmware_id>/limits')
@login_required
def route_limits(firmware_id):

    # get details about the firmware
    fw = db.session.query(Firmware).\
            filter(Firmware.firmware_id == firmware_id).first()
    if not fw:
        flash('No firmware matched!', 'danger')
        return redirect(url_for('firmware.route_firmware'))

    # security check
    if not fw.check_acl('@view'):
        flash('Permission denied: Insufficient permissions to view limits', 'danger')
        return redirect(url_for('firmware.route_show', firmware_id=firmware_id))

    return render_template('firmware-limits.html',
                           category='firmware',
                           fw=fw)

@bp_firmware.route('/limit/<int:firmware_limit_id>/delete', methods=['POST'])
@login_required
def route_limit_delete(firmware_limit_id):

    # get details about the firmware
    fl = db.session.query(FirmwareLimit).\
            filter(FirmwareLimit.firmware_limit_id == firmware_limit_id).first()
    if not fl:
        flash('No firmware limit matched!', 'danger')
        return redirect(url_for('firmware.route_firmware'))

    # security check
    if not fl.fw.check_acl('delete-limit'):
        flash('Permission denied: Insufficient permissions to delete limits', 'danger')
        return redirect(url_for('firmware.route_firmware'))

    firmware_id = fl.firmware_id
    fl.fw.mark_dirty()
    db.session.delete(fl)
    db.session.commit()
    flash('Deleted limit', 'info')

    # asynchronously sign
    _async_regenerate_remote.apply_async(args=(fl.fw.remote.remote_id,), queue='metadata')

    return redirect(url_for('firmware.route_limits', firmware_id=firmware_id))

@bp_firmware.route('/<int:firmware_id>/modify', methods=['POST'])
@login_required
def route_modify(firmware_id):
    """ Modifies the firmware properties """

    # find firmware
    fw = db.session.query(Firmware).filter(Firmware.firmware_id == firmware_id).first()
    if not fw:
        return _error_internal("No firmware %s" % firmware_id)

    # security check
    if not fw.check_acl('@modify'):
        flash('Permission denied: Insufficient permissions to modify firmware', 'danger')
        return redirect(url_for('firmware.route_show', firmware_id=firmware_id))

    # set new metadata values
    if 'failure_minimum' in request.form:
        fw.failure_minimum = request.form['failure_minimum']
    if 'failure_percentage' in request.form:
        fw.failure_percentage = request.form['failure_percentage']

    # modify
    db.session.commit()
    flash('Firmware updated', 'info')
    return redirect(url_for('firmware.route_limits',
                            firmware_id=firmware_id))

@bp_firmware.route('/limit/create', methods=['POST'])
@login_required
def route_limit_create():

    # get details about the firmware
    fw = db.session.query(Firmware).\
            filter(Firmware.firmware_id == request.form['firmware_id']).first()
    if not fw:
        flash('No firmware matched!', 'danger')
        return redirect(url_for('firmware.route_firmware'))

    # security check
    if not fw.check_acl('@modify-limit'):
        flash('Permission denied: Unable to add restriction', 'danger')
        return redirect(url_for('firmware.route_show', firmware_id=fw.firmware_id))

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

    # asynchronously sign
    _async_regenerate_remote.apply_async(args=(fl.fw.remote.remote_id,), queue='metadata')

    return redirect(url_for('firmware.route_limits', firmware_id=fl.firmware_id))

@bp_firmware.route('/<int:firmware_id>/affiliation')
@login_required
def route_affiliation(firmware_id):

    # get details about the firmware
    fw = db.session.query(Firmware).\
            filter(Firmware.firmware_id == firmware_id).first()
    if not fw:
        flash('No firmware matched!', 'danger')
        return redirect(url_for('firmware.route_firmware'))

    # security check
    if not fw.check_acl('@modify-affiliation'):
        flash('Permission denied: Insufficient permissions to modify affiliations', 'danger')
        return redirect(url_for('firmware.route_show', firmware_id=firmware_id))

    # add other vendors
    if g.user.check_acl('@admin'):
        vendors = []
        for v in db.session.query(Vendor).order_by(Vendor.display_name):
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

@bp_firmware.route('/<int:firmware_id>/affiliation/change', methods=['POST'])
@login_required
def route_affiliation_change(firmware_id):
    """ Changes the assigned vendor ID for the firmware """

    # change the vendor
    if 'vendor_id' not in request.form:
        return _error_internal('No vendor ID specified')

    # find firmware
    fw = db.session.query(Firmware).filter(Firmware.firmware_id == firmware_id).first()
    if not fw:
        flash('No firmware matched!', 'danger')
        return redirect(url_for('firmware.route_firmware'))

    # security check
    if not fw.check_acl('@modify-affiliation'):
        flash('Permission denied: Insufficient permissions to change affiliation', 'danger')
        return redirect(url_for('firmware.route_show', firmware_id=firmware_id))

    vendor_id = int(request.form['vendor_id'])
    if vendor_id == fw.vendor_id:
        flash('No affiliation change required', 'info')
        return redirect(url_for('firmware.route_affiliation', firmware_id=fw.firmware_id))
    if not g.user.check_acl('@admin') and \
        not g.user.vendor.is_affiliate_for(vendor_id) and \
        vendor_id != g.user.vendor_id:
        flash('Insufficient permissions to change affiliation to {}'.format(vendor_id), 'danger')
        return redirect(url_for('firmware.route_show', firmware_id=firmware_id))
    old_vendor = fw.vendor
    fw.vendor_id = vendor_id
    db.session.commit()

    # do we need to regenerate remotes?
    if fw.remote.name.startswith('embargo'):
        fw.vendor.remote.is_dirty = True
        fw.user.vendor.remote.is_dirty = True
        old_vendor.remote.is_dirty = True
        fw.remote_id = fw.vendor.remote.remote_id
        fw.events.append(FirmwareEvent(remote_id=fw.remote_id, user_id=g.user.user_id))
        fw.mark_dirty()
        db.session.commit()

    flash('Changed firmware vendor', 'info')

    # asynchronously sign
    _async_regenerate_remote.apply_async(args=(fw.remote.remote_id,), queue='metadata')

    return redirect(url_for('firmware.route_show', firmware_id=fw.firmware_id))

@bp_firmware.route('/<int:firmware_id>/problems')
@login_required
def route_problems(firmware_id):

    # get details about the firmware
    fw = db.session.query(Firmware).\
            filter(Firmware.firmware_id == firmware_id).first()
    if not fw:
        flash('No firmware matched!', 'danger')
        return redirect(url_for('firmware.route_firmware'))

    # security check
    if not fw.check_acl('@view'):
        flash('Permission denied: Insufficient permissions to view components', 'danger')
        return redirect(url_for('firmware.route_firmware'))

    return render_template('firmware-problems.html',
                           category='firmware',
                           fw=fw)

@bp_firmware.route('/<int:firmware_id>/target')
@login_required
def route_target(firmware_id):

    # get details about the firmware
    fw = db.session.query(Firmware).\
            filter(Firmware.firmware_id == firmware_id).first()
    if not fw:
        flash('No firmware matched!', 'danger')
        return redirect(url_for('firmware.route_firmware'))

    # security check
    if not fw.check_acl('@view'):
        flash('Permission denied: Insufficient permissions to view firmware', 'danger')
        return redirect(url_for('firmware.route_firmware'))

    return render_template('firmware-target.html',
                           category='firmware',
                           fw=fw)

@bp_firmware.route('/<int:firmware_id>')
@login_required
def route_show(firmware_id):
    """ Show firmware information """

    # get details about the firmware
    fw = db.session.query(Firmware).\
            filter(Firmware.firmware_id == firmware_id).\
            first()
    if not fw:
        flash('No firmware matched!', 'danger')
        return redirect(url_for('firmware.route_firmware'))

    # security check
    if not fw.check_acl('@view'):
        flash('Permission denied: Insufficient permissions to view firmware', 'danger')
        return redirect(url_for('firmware.route_firmware'))

    # get data for the last month or year
    graph_data = []
    graph_labels = None
    if fw.check_acl('@view-analytics') and not fw.do_not_track:
        if fw.timestamp.replace(tzinfo=None) > datetime.datetime.today() - datetime.timedelta(days=30):
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

@bp_firmware.route('/<int:firmware_id>/analytics')
@bp_firmware.route('/<int:firmware_id>/analytics/clients')
@login_required
def route_analytics_clients(firmware_id):
    """ Show firmware clients information """

    # get details about the firmware
    fw = db.session.query(Firmware).filter(Firmware.firmware_id == firmware_id).first()
    if not fw:
        flash('No firmware matched!', 'danger')
        return redirect(url_for('firmware.route_firmware'))

    # security check
    if not fw.check_acl('@view-analytics'):
        flash('Permission denied: Insufficient permissions to view analytics', 'danger')
        return redirect(url_for('firmware.route_show', firmware_id=firmware_id))
    clients = db.session.query(Client).filter(Client.firmware_id == fw.firmware_id).\
                order_by(Client.id.desc()).limit(10).all()
    return render_template('firmware-analytics-clients.html',
                           category='firmware',
                           fw=fw,
                           clients=clients)

@bp_firmware.route('/<int:firmware_id>/analytics/reports')
@bp_firmware.route('/<int:firmware_id>/analytics/reports/<int:state>')
@bp_firmware.route('/<int:firmware_id>/analytics/reports/<int:state>/<int:limit>')
@login_required
def route_analytics_reports(firmware_id, state=None, limit=100):
    """ Show firmware clients information """

    # get reports about the firmware
    fw = db.session.query(Firmware).filter(Firmware.firmware_id == firmware_id).first()
    if not fw:
        flash('No firmware matched!', 'danger')
        return redirect(url_for('firmware.route_firmware'))

    # security check
    if not fw.check_acl('@view-analytics'):
        flash('Permission denied: Insufficient permissions to view analytics', 'danger')
        return redirect(url_for('firmware.route_show', firmware_id=firmware_id))
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

@bp_firmware.route('/<int:firmware_id>/tests')
@login_required
def route_tests(firmware_id):

    # get details about the firmware
    fw = db.session.query(Firmware).\
            filter(Firmware.firmware_id == firmware_id).first()
    if not fw:
        flash('No firmware matched!', 'danger')
        return redirect(url_for('firmware.route_firmware'))

    # security check
    if not fw.check_acl('@view'):
        flash('Permission denied: Insufficient permissions to view firmware', 'danger')
        return redirect(url_for('firmware.route_firmware'))

    return render_template('firmware-tests.html',
                           category='firmware',
                           fw=fw)

@bp_firmware.route('/shard/search/<kind>/<value>')
@login_required
def route_shard_search(kind, value):
    """
    Show firmware with shards that match the value
    """

    if kind == 'guid':
        fws = db.session.query(Firmware).\
                    join(Component).\
                    join(ComponentShard).\
                    filter(ComponentShard.guid == value).\
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
