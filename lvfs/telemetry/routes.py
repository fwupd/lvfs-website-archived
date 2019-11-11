#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2017-2018 Richard Hughes <richard@hughsie.com>
#
# SPDX-License-Identifier: GPL-2.0+

import datetime

from flask import Blueprint, render_template, g, flash, redirect, url_for
from flask_login import login_required

from lvfs import db

from lvfs.models import Firmware

bp_telemetry = Blueprint('telemetry', __name__, template_folder='templates')

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

@bp_telemetry.route('/<int:age>/<sort_key>/<sort_direction>')
@bp_telemetry.route('/<int:age>/<sort_key>')
@bp_telemetry.route('/<int:age>')
@bp_telemetry.route('/')
@login_required
def route_show(age=0, sort_key='success', sort_direction='down'):
    """ Show firmware component information """

    # only Analyst users can view this data
    if not g.user.check_acl('@view-analytics'):
        flash('Permission denied: Unable to view telemetry as not Analyst', 'danger')
        return redirect(url_for('main.route_dashboard'))

    # get data
    fws = []
    stmt = db.session.query(Firmware)
    if age:
        stmt = stmt.filter(Firmware.timestamp > datetime.date.today() - datetime.timedelta(days=age))
    for fw in stmt:

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
