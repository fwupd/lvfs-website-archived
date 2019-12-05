#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2017-2018 Richard Hughes <richard@hughsie.com>
#
# SPDX-License-Identifier: GPL-2.0+

import datetime

from flask import Blueprint, render_template, flash, redirect, url_for
from flask_login import login_required

from sqlalchemy import func

from lvfs import db

from lvfs.util import admin_login_required
from lvfs.models import Firmware, Component, Remote, Guid

bp_devices = Blueprint('devices', __name__, template_folder='templates')

@bp_devices.route('/admin')
@login_required
@admin_login_required
def route_list_admin():
    """
    Show all devices -- probably only useful for the admin user.
    """

    # get all the appstream_ids we can target
    devices = []
    seen_appstream_id = {}
    for fw in db.session.query(Firmware):
        for md in fw.mds:
            if md.appstream_id in seen_appstream_id:
                continue
            seen_appstream_id[md.appstream_id] = 1
            devices.append(md.appstream_id)

    return render_template('devices.html', devices=devices)

def _dt_from_quarter(year, quarter):
    month = (quarter * 3) + 1
    if month > 12:
        month %= 12
        year += 1
    return datetime.datetime(year, month, 1)

def _get_fws_for_appstream_id(value):

    # old, deprecated GUID view
    if len(value.split('-')) == 5:
        return db.session.query(Firmware).\
                    join(Remote).filter(Remote.is_public).\
                    join(Component).join(Guid).filter(Guid.value == value).\
                    order_by(Firmware.timestamp.desc()).all()

    # new, AppStream ID view
    return db.session.query(Firmware).\
                    join(Remote).filter(Remote.is_public).\
                    join(Component).filter(Component.appstream_id == value).\
                    order_by(Firmware.timestamp.desc()).all()

@bp_devices.route('/<appstream_id>')
def route_show(appstream_id):
    """
    Show information for one device, which can be seen without a valid login
    """
    fws = _get_fws_for_appstream_id(appstream_id)

    # work out the previous version for the shard diff
    fw_old = None
    fw_previous = {}
    for fw in fws:
        if fw_old:
            fw_previous[fw_old] = fw
        fw_old = fw

    return render_template('device.html',
                           appstream_id=appstream_id,
                           fws=fws,
                           fw_previous=fw_previous)

@bp_devices.route('/<appstream_id>/atom')
def route_show_atom(appstream_id):
    """
    Show information for one device, which can be seen without a valid login
    """
    fws = _get_fws_for_appstream_id(appstream_id)

    # work out the previous version for the shard diff
    fw_old = None
    fw_previous = {}
    for fw in fws:
        if fw_old:
            fw_previous[fw_old] = fw
        fw_old = fw

    return render_template('device-atom.xml',
                           appstream_id=appstream_id,
                           fws=fws,
                           fw_previous=fw_previous)

@bp_devices.route('/component/<int:component_id>')
def route_shards(component_id):
    """
    Show information for one firmware, which can be seen without a valid login
    """
    md = db.session.query(Component).filter(Component.component_id == component_id).first()
    if not md:
        flash('No component with ID {} exists'.format(component_id), 'danger')
        return redirect(url_for('devices.route_show', appstream_id=md.appstream_id))
    return render_template('device-shards.html', md=md, appstream_id=md.appstream_id)

@bp_devices.route('/component/<int:component_id_old>/<int:component_id_new>')
def route_shards_diff(component_id_old, component_id_new):
    """
    Show information for one firmware, which can be seen without a valid login
    """
    md_old = db.session.query(Component).filter(Component.component_id == component_id_old).first()
    if not md_old:
        flash('No component with ID {} exists'.format(component_id_old), 'danger')
        return redirect(url_for('devices.route_list_admin'))
    md_new = db.session.query(Component).filter(Component.component_id == component_id_new).first()
    if not md_new:
        flash('No component with ID {} exists'.format(component_id_new), 'danger')
        return redirect(url_for('devices.route_list_admin'))

    # shards added
    shard_guids = {}
    for shard in md_old.shards:
        shard_guids[shard.guid] = shard
    shards_added = []
    for shard in md_new.shards:
        if shard.guid not in shard_guids:
            shards_added.append(shard)

    # shards removed
    shard_guids = {}
    for shard in md_new.shards:
        shard_guids[shard.guid] = shard
    shards_removed = []
    for shard in md_old.shards:
        if shard.guid not in shard_guids:
            shards_removed.append(shard)

    # shards changed
    shard_checksums = {}
    for shard in md_new.shards:
        shard_checksums[shard.checksum] = shard
    shards_changed = []
    for shard in md_old.shards:
        if shard.guid in shard_guids:
            shard_old = shard_guids[shard.guid]
            if shard.checksum not in shard_checksums:
                shards_changed.append((shard_old, shard))

    return render_template('device-shards-diff.html',
                           md_old=md_old, md_new=md_new,
                           shards_added=shards_added,
                           shards_removed=shards_removed,
                           shards_changed=shards_changed,
                           appstream_id=md_old.appstream_id)

@bp_devices.route('/<appstream_id>/analytics')
def route_analytics(appstream_id):
    """
    Show analytics for one device, which can be seen without a valid login
    """
    data = []
    labels = []
    now = datetime.date.today()
    fws = _get_fws_for_appstream_id(appstream_id)
    if not fws:
        flash('No firmware with that AppStream ID or GUID exists', 'danger')
        return redirect(url_for('devices.route_list_admin'))
    for i in range(-2, 1):
        year = now.year + i
        for quarter in range(0, 4):
            t1 = _dt_from_quarter(year, quarter)
            t2 = _dt_from_quarter(year, quarter + 1)
            cnt = 0
            for fw in fws:
                if fw.timestamp >= t1 and fw.timestamp < t2:
                    cnt += 1
            labels.append("%04iQ%i" % (year, quarter + 1))
            data.append(cnt)

    return render_template('device-analytics.html',
                           appstream_id=appstream_id,
                           labels=labels,
                           data=data,
                           fws=fws)

@bp_devices.route('/')
def route_list():

    # get a list of firmwares with a map of components
    fws = db.session.query(Firmware).\
                           join(Remote).filter(Remote.is_public).\
                           join(Component).group_by(Component.appstream_id).\
                           order_by(Firmware.timestamp.desc()).\
                           distinct(Component.name).all()
    vendors = []
    mds_by_vendor = {}
    for fw in fws:
        vendor = fw.md_prio.developer_name
        if vendor not in vendors:
            vendors.append(vendor)
        if not vendor in mds_by_vendor:
            mds_by_vendor[vendor] = []
        mds_by_vendor[vendor].append(fw.md_prio)

    # ensure list is sorted
    for vendor in mds_by_vendor:
        mds_by_vendor[vendor].sort(key=lambda obj: obj.name)

    # get most recent supported devices
    fws_recent = db.session.query(Firmware).\
                                  join(Remote).filter(Remote.is_public).\
                                  join(Component).group_by(Component.name).\
                                  having(func.count() == 1).\
                                  order_by(Firmware.timestamp.desc()).\
                                  limit(6).all()

    return render_template('devicelist.html',
                           vendors=sorted(vendors),
                           devices=fws_recent,
                           mds_by_vendor=mds_by_vendor)
