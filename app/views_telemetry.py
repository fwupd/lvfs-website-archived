#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2017-2018 Richard Hughes <richard@hughsie.com>
#
# SPDX-License-Identifier: GPL-2.0+

import datetime

from flask import render_template, g
from flask_login import login_required

from app import app, db

from .models import Firmware
from .util import _error_permission_denied

def _get_split_names_for_firmware(fw):
    names = []
    for md in fw.mds:
        name_split = md.name.split('/')
        all_substrings_long_enough = True
        for name in name_split:
            if len(name) < 8:
                all_substrings_long_enough = False
                break
        if all_substrings_long_enough:
            for name in name_split:
                names.append(name)
        else:
            names.append(md.name)
    return sorted(names)

@app.route('/lvfs/telemetry/<int:age>/<sort_key>/<sort_direction>')
@app.route('/lvfs/telemetry/<int:age>/<sort_key>')
@app.route('/lvfs/telemetry/<int:age>')
@app.route('/lvfs/telemetry')
@login_required
def telemetry(age=0, sort_key='success', sort_direction='down'):
    """ Show firmware component information """

    # only Analyst users can view this data
    if not g.user.check_acl('@view-analytics'):
        return _error_permission_denied('Unable to view telemetry as not Analyst')

    # get data
    fws = []
    stmt = db.session.query(Firmware)
    if age:
        stmt = stmt.filter(Firmware.timestamp > datetime.date.today() - datetime.timedelta(days=age))
    for fw in stmt.all():

        # not allowed to view
        if not g.user.check_acl('@admin') and fw.vendor.group_id != g.user.vendor.group_id:
            continue
        if len(fw.mds) == 0:
            continue
        if not fw.remote.is_public:
            continue
        if not fw.download_cnt:
            continue
        if sort_key == 'success':
            if not fw.report_success_cnt and not fw.report_failure_cnt:
                continue
        fws.append(fw)

    if sort_direction == 'down':
        fws.sort(key=lambda x: getattr(x, 'download_cnt'))
        fws.sort(key=lambda x: getattr(x, sort_key) or 1)
    else:
        fws.sort(key=lambda x: getattr(x, 'download_cnt'), reverse=True)
        fws.sort(key=lambda x: getattr(x, sort_key) or 1, reverse=True)
    return render_template('telemetry.html',
                           category='telemetry',
                           age=age,
                           sort_key=sort_key,
                           sort_direction=sort_direction,
                           fws=fws,
                           group_id=g.user.vendor.group_id)
