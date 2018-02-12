#!/usr/bin/python2
# -*- coding: utf-8 -*-
#
# Copyright (C) 2017-2018 Richard Hughes <richard@hughsie.com>
# Licensed under the GNU General Public License Version 2

from flask import url_for, redirect, render_template, g
from flask_login import login_required
from sqlalchemy import func, text

from app import app, db

from .db import _execute_count_star
from .models import Firmware, Client, Report, UserCapability
from .util import _error_permission_denied

def _get_split_names_for_firmware(fw):
    names = []
    for md in fw.mds:
        name_safe = md.name.replace(' System Update', '')
        name_split = name_safe.split('/')
        all_substrings_long_enough = True
        for name in name_split:
            if len(name) < 8:
                all_substrings_long_enough = False
                break
        if all_substrings_long_enough:
            for name in name_split:
                names.append(name)
        else:
            names.append(name_safe)
    return sorted(names)

@app.route('/lvfs/telemetry/repair')
@login_required
def telemetry_repair():
    if not g.user.check_capability(UserCapability.Admin):
        return _error_permission_denied('Not admin user')
    for fw in db.session.query(Firmware).all():
        q = db.session.query(Client).filter(Client.filename == fw.filename)
        count_q = q.statement.with_only_columns([func.count()]).order_by(None)
        fw.download_cnt = q.session.execute(count_q).scalar()
    db.session.commit()
    return redirect(url_for('.telemetry'))

@app.route('/lvfs/telemetry/<int:age>/<sort_key>/<sort_direction>')
@app.route('/lvfs/telemetry/<int:age>/<sort_key>')
@app.route('/lvfs/telemetry/<int:age>')
@app.route('/lvfs/telemetry')
@login_required
def telemetry(age=0, sort_key='downloads', sort_direction='up'):
    """ Show firmware component information """

    # only Analyst users can view this data
    if not g.user.check_capability(UserCapability.Analyst):
        return _error_permission_denied('Unable to view telemetry as not Analyst')

    # get data
    total_downloads = 0
    total_success = 0
    total_failed = 0
    total_issue = 0
    show_duplicate_warning = False
    fwlines = []
    for fw in db.session.query(Firmware).all():

        # not allowed to view
        if not g.user.check_capability(UserCapability.Admin) and fw.group_id != g.user.group_id:
            continue
        if len(fw.mds) == 0:
            continue
        if fw.target == 'private' or fw.target == 'embargo':
            continue

        # reports
        if age == 0:
            cnt_download = fw.download_cnt
            rpts = db.session.query(Report).\
                        filter(Report.firmware_id == fw.firmware_id).all()
        else:
            cnt_download = _execute_count_star(db.session.query(Client).\
                                filter(Client.filename == fw.filename).\
                                filter(func.timestampdiff(text('DAY'),
                                                          Client.timestamp,
                                                          func.current_timestamp()) < age))
            rpts = db.session.query(Report).\
                        filter(Report.firmware_id == fw.firmware_id).\
                        filter(func.timestampdiff(text('DAY'),
                                                  Report.timestamp,
                                                  func.current_timestamp()) < age).all()

        cnt_success = 0
        cnt_failed = 0
        cnt_issue = 0
        for rpt in rpts:
            if rpt.state == 2:
                cnt_success += 1
            if rpt.state == 3:
                if rpt.issue_id:
                    cnt_issue += 1
                else:
                    cnt_failed += 1
        total_success += cnt_success
        total_failed += cnt_failed
        total_issue += cnt_issue
        total_downloads += cnt_download

        # add lines
        res = {}
        res['downloads'] = cnt_download
        res['success'] = cnt_success
        res['failed'] = cnt_failed
        res['issue'] = cnt_issue
        res['names'] = _get_split_names_for_firmware(fw)
        res['version'] = fw.version_display
        if not res['version']:
            res['version'] = fw.mds[0].version
        res['nameversion'] = res['names'][0] + ' ' + res['version']
        res['firmware_id'] = fw.firmware_id
        res['target'] = fw.target
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
                           age=age,
                           sort_key=sort_key,
                           sort_direction=sort_direction,
                           firmware=fwlines,
                           group_id=g.user.group_id,
                           show_duplicate_warning=show_duplicate_warning,
                           total_failed=total_failed,
                           total_issue=total_issue,
                           total_downloads=total_downloads,
                           total_success=total_success)
