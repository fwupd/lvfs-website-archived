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
from lvfs.models import User
from lvfs.util import _event_log

def _user_disable_notify():

    # find all users that have not logged in for over one year, and have never
    # been warned
    now = datetime.datetime.utcnow()
    for user in db.session.query(User)\
                          .filter(User.auth_type != 'disabled')\
                          .filter(User.atime < now - datetime.timedelta(days=365))\
                          .filter(User.unused_notify_ts == None):
        # send email
        send_email("[LVFS] User account unused: ACTION REQUIRED",
                   user.email_address,
                   render_template('email-unused.txt',
                                   user=user))
        user.unused_notify_ts = now
        db.session.commit()

def _user_disable_actual():

    # find all users that have an atime greater than 1 year and unused_notify_ts > 6 weeks */
    now = datetime.datetime.utcnow()
    for user in db.session.query(User)\
                          .filter(User.auth_type != 'disabled')\
                          .filter(User.atime < now - datetime.timedelta(days=365))\
                          .filter(User.unused_notify_ts < now - datetime.timedelta(days=42)):
        _event_log('Disabling user {} {} ({}) as unused'.format(user.user_id,
                                                                user.username,
                                                                user.display_name))
        user.auth_type = 'disabled'
        user.username = 'disabled_user{}@fwupd.org'.format(user.user_id)
        user.display_name = 'Disabled User {}'.format(user.user_id)
        db.session.commit()

def _user_email_report():

    # find all users
    for user in db.session.query(User)\
                          .filter(User.auth_type != 'disabled'):
        if not user.get_action('notify-non-public'):
            continue
        fws_embargo = []
        fws_testing = []
        for fw in user.fws:
            if fw.target_duration < datetime.timedelta(days=30):
                continue
            if fw.remote.name == 'testing':
                fws_testing.append(fw)
                continue
            if fw.remote.name.startswith('embargo'):
                fws_embargo.append(fw)
                continue
        if fws_embargo or fws_testing:
            send_email("[LVFS] List of non-public firmware",
                       user.email_address,
                       render_template('email-non-public.txt',
                                       user=user,
                                       fws_embargo=fws_embargo,
                                       fws_testing=fws_testing))

@celery.task(max_retries=3, default_retry_delay=60, task_time_limit=120)
def _async_user_disable():
    _user_disable_notify()
    _user_disable_actual()

@celery.task(max_retries=3, default_retry_delay=60, task_time_limit=120)
def _async_user_email_report():
    _user_email_report()
