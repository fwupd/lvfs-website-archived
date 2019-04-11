#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2017-2018 Richard Hughes <richard@hughsie.com>
# Licensed under the GNU General Public License Version 2

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
def telemetry(age=0, sort_key='downloads', sort_direction='up'):
    """ Show firmware component information """

    # only Analyst users can view this data
    if not g.user.check_acl('@view-analytics'):
        return _error_permission_denied('Unable to view telemetry as not Analyst')

    # get data
    total_downloads = 0
    total_success = 0
    total_failed = 0
    total_issue = 0
    show_duplicate_warning = False
    fwlines = []
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

        # add lines
        res = {}
        res['downloads'] = fw.download_cnt
        res['success'] = fw.report_success_cnt
        res['failed'] = fw.report_failure_cnt
        res['issue'] = fw.report_issue_cnt
        res['names'] = _get_split_names_for_firmware(fw)
        res['version'] = fw.version_display
        if not res['version']:
            res['version'] = fw.md_prio.version
        res['nameversion'] = res['names'][0] + ' ' + res['version']
        res['firmware_id'] = fw.firmware_id
        res['target'] = fw.remote.name
        res['duplicate'] = len(fw.mds)
        fwlines.append(res)

        # show the user a warning
        if len(fw.mds) > 1:
            show_duplicate_warning = True

    if sort_direction == 'down':
        fwlines.sort(key=lambda x: x['downloads'])
        fwlines.sort(key=lambda x: x[sort_key])
    else:
        fwlines.sort(key=lambda x: x['downloads'], reverse=True)
        fwlines.sort(key=lambda x: x[sort_key], reverse=True)
    return render_template('telemetry.html',
                           category='telemetry',
                           age=age,
                           sort_key=sort_key,
                           sort_direction=sort_direction,
                           firmware=fwlines,
                           group_id=g.user.vendor.group_id,
                           show_duplicate_warning=show_duplicate_warning,
                           total_failed=total_failed,
                           total_issue=total_issue,
                           total_downloads=total_downloads,
                           total_success=total_success)
