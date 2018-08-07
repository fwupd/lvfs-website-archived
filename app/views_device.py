#!/usr/bin/python2
# -*- coding: utf-8 -*-
#
# Copyright (C) 2017-2018 Richard Hughes <richard@hughsie.com>
# Licensed under the GNU General Public License Version 2

import datetime

from flask import render_template, g
from flask_login import login_required

from app import app, db

from .util import _error_permission_denied
from .models import Firmware

@app.route('/lvfs/device')
@login_required
def device():
    """
    Show all devices -- probably only useful for the admin user.
    """

    # security check
    if not g.user.check_acl('@admin'):
        return _error_permission_denied('Unable to view devices')

    # get all the guids we can target
    devices = []
    seen_guid = {}
    for fw in db.session.query(Firmware).all():
        for md in fw.mds:
            if md.guids[0].value in seen_guid:
                continue
            seen_guid[md.guids[0].value] = 1
            devices.append(md.guids[0].value)

    return render_template('devices.html', devices=devices)

def _dt_from_quarter(year, quarter):
    month = (quarter * 3) + 1
    if month > 12:
        month %= 12
        year += 1
    return datetime.datetime(year, month, 1)

def _get_fws_for_guid(guid):
    # get all the guids we can target
    fws = []
    for fw in db.session.query(Firmware).\
                    order_by(Firmware.timestamp.desc()).all():
        if fw.is_deleted:
            continue
        if not fw.mds:
            continue
        for md in fw.mds:
            if md.guids[0].value != guid:
                continue
            fws.append(fw)
            break
    return fws

@app.route('/lvfs/device/<guid>')
def device_guid(guid):
    """
    Show information for one device, which can be seen without a valid login
    """
    fws = _get_fws_for_guid(guid)
    return render_template('device.html', guid=guid, fws=fws)

@app.route('/lvfs/device/<guid>/analytics')
def device_analytics(guid):
    """
    Show analytics for one device, which can be seen without a valid login
    """
    data = []
    labels = []
    now = datetime.date.today()
    fws = _get_fws_for_guid(guid)
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
                           guid=guid,
                           labels=labels,
                           data=data,
                           fws=fws)

@app.route('/lvfs/devicelist')
def device_list():

    # get a sorted list of vendors
    fws = db.session.query(Firmware).all()
    vendors = []
    for fw in fws:
        if not fw.remote.is_public:
            continue
        vendor = fw.mds[0].developer_name
        if vendor in vendors:
            continue
        vendors.append(vendor)

    seen_ids = {}
    mds_by_vendor = {}
    for vendor in sorted(vendors):
        for fw in fws:
            if not fw.remote.is_public:
                continue
            for md in fw.mds:

                # only show correct vendor
                if vendor != md.developer_name:
                    continue

                # only show the newest version
                if md.appstream_id in seen_ids:
                    continue
                seen_ids[md.appstream_id] = 1

                # add
                if not vendor in mds_by_vendor:
                    mds_by_vendor[vendor] = []
                mds_by_vendor[vendor].append(md)

    # ensure list is sorted
    for vendor in mds_by_vendor:
        mds_by_vendor[vendor].sort(key=lambda obj: obj.name)

    return render_template('devicelist.html',
                           vendors=sorted(vendors),
                           mds_by_vendor=mds_by_vendor)
