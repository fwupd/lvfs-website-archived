#!/usr/bin/python2
# -*- coding: utf-8 -*-
#
# Copyright (C) 2017 Richard Hughes <richard@hughsie.com>
# Licensed under the GNU General Public License Version 2

from flask import render_template, g
from flask_login import login_required

from app import app, db

from .util import _error_internal, _error_permission_denied
from .db import CursorError

@app.route('/lvfs/device')
@login_required
def device():
    """
    Show all devices -- probably only useful for the admin user.
    """

    # security check
    if g.user.group_id != 'admin':
        return _error_permission_denied('Unable to view devices')

    # get all firmware
    try:
        items = db.firmware.get_all()
    except CursorError as e:
        return _error_internal(str(e))

    # get all the guids we can target
    devices = []
    seen_guid = {}
    for item in items:
        for md in item.mds:
            if md.guids[0] in seen_guid:
                continue
            seen_guid[md.guids[0]] = 1
            devices.append(md.guids[0])

    return render_template('devices.html', devices=devices)

@app.route('/lvfs/device/<guid>')
def device_guid(guid):
    """
    Show information for one device, which can be seen without a valid login
    """

    # get all firmware
    try:
        items = db.firmware.get_all()
    except CursorError as e:
        return _error_internal(str(e))

    # get all the guids we can target
    firmware_items = []
    for item in items:
        for md in item.mds:
            if md.guids[0] != guid:
                continue
            firmware_items.append(item)
            break

    return render_template('device.html', items=firmware_items)


@app.route('/lvfs/devicelist')
def device_list():
    # add devices in stable or testing
    try:
        items = db.firmware.get_all()
    except CursorError as e:
        return _error_internal(str(e))

    # get a sorted list of vendors
    vendors = []
    for item in items:
        if item.target not in ['stable', 'testing']:
            continue
        vendor = item.mds[0].developer_name
        if vendor in vendors:
            continue
        vendors.append(vendor)

    seen_ids = {}
    mds_by_vendor = {}
    for vendor in sorted(vendors):
        for item in items:
            if item.target not in ['stable', 'testing']:
                continue
            for md in item.mds:

                # only show correct vendor
                if vendor != md.developer_name:
                    continue

                # only show the newest version
                if md.cid in seen_ids:
                    continue
                seen_ids[md.cid] = 1

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
