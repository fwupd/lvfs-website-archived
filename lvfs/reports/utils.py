#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2019-2020 Richard Hughes <richard@hughsie.com>
#
# SPDX-License-Identifier: GPL-2.0+
#
# pylint: disable=singleton-comparison

import datetime

from flask import render_template

from lvfs import db, celery

from lvfs.emails import send_email
from lvfs.models import Report, User, Remote, FirmwareEvent, Firmware
from lvfs.util import _event_log
from lvfs.metadata.utils import _async_regenerate_remote

def _demote_back_to_testing(fw):

    # from the server admin
    user = db.session.query(User).filter(User.username == 'anon@fwupd.org').first()
    if not user:
        return

    # send email to uploading user
    if fw.user.get_action('notify-demote-failures'):
        send_email("[LVFS] Firmware has been demoted",
                   fw.user.email_address,
                   render_template('email-firmware-demote.txt',
                                   user=fw.user, fw=fw))

    fw.mark_dirty()
    remote = db.session.query(Remote).filter(Remote.name == 'testing').first()
    remote.is_dirty = True

    # asynchronously sign straight away, even public remotes
    for r in set([remote, fw.remote]):
        r.is_dirty = True
        db.session.commit()
        _async_regenerate_remote.apply_async(args=(r.remote_id,), queue='metadata', countdown=1)

    fw.remote_id = remote.remote_id
    fw.events.append(FirmwareEvent(remote_id=fw.remote_id, user_id=user.user_id))
    db.session.commit()
    _event_log('Demoted firmware {} as reported success {}%'.format(fw.firmware_id, fw.success))

def _generate_stats_firmware_reports(fw):

    # count how many times any of the firmware files were downloaded
    reports_success = 0
    reports_failure = 0
    reports_issue = 0
    for r in db.session.query(Report).\
                    filter(Report.firmware_id == fw.firmware_id,
                           Report.timestamp > datetime.date.today() - datetime.timedelta(weeks=26)):
        if r.state == 2:
            reports_success += 1
        if r.state == 3:
            if r.issue_id:
                reports_issue += 1
            else:
                reports_failure += 1

    # update
    fw.report_success_cnt = reports_success
    fw.report_failure_cnt = reports_failure
    fw.report_issue_cnt = reports_issue

    # check the limits and demote back to embargo if required
    if fw.remote.name == 'stable' and fw.is_failure:
        _demote_back_to_testing(fw)

def _regenerate_reports():

    # update FirmwareReport counts
    for firmware_id, in db.session.query(Firmware.firmware_id)\
                                  .join(Remote).filter(Remote.name != 'deleted')\
                                  .order_by(Firmware.firmware_id.asc()):
        fw = db.session.query(Firmware)\
                       .filter(Firmware.firmware_id == firmware_id)\
                       .one()
        _generate_stats_firmware_reports(fw)
    db.session.commit()

@celery.task(max_retries=3, default_retry_delay=60, task_time_limit=600)
def _async_regenerate_reports():
    _regenerate_reports()
