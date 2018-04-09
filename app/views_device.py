#!/usr/bin/python2
# -*- coding: utf-8 -*-
#
# Copyright (C) 2017-2018 Richard Hughes <richard@hughsie.com>
# Licensed under the GNU General Public License Version 2

from flask import render_template, g
from flask_login import login_required

from app import app, db

from .util import _error_permission_denied
from .models import UserCapability, Firmware

@app.route('/lvfs/device')
@login_required
def device():
    """
    Show all devices -- probably only useful for the admin user.
    """

    # security check
    if not g.user.check_capability(UserCapability.Admin):
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

@app.route('/lvfs/device/<guid>')
def device_guid(guid):
    """
    Show information for one device, which can be seen without a valid login
    """

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

    return render_template('device.html', fws=fws)


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
