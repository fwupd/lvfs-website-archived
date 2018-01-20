#!/usr/bin/python2
# -*- coding: utf-8 -*-
#
# Copyright (C) 2015 Richard Hughes <richard@hughsie.com>
# Licensed under the GNU General Public License Version 2

import os
import sys
import calendar
import datetime

from flask import session, request, flash, render_template

from app import app, db

from .affidavit import Affidavit

def _create_affidavit():
    """ Create an affidavit that can be used to sign files """
    key_uid = db.users.get_signing_uid()
    return Affidavit(key_uid, app.config['KEYRING_DIR'])

def _get_client_address():
    """ Gets user IP address """
    if request.headers.getlist("X-Forwarded-For"):
        return request.headers.getlist("X-Forwarded-For")[0]
    return request.remote_addr

def _event_log(msg, is_important=False):
    """ Adds an item to the event log """
    username = None
    group_id = None
    request_path = None
    if 'username' in session:
        username = session['username']
    if not username:
        username = 'anonymous'
    if 'group_id' in session:
        group_id = session['group_id']
    if not group_id:
        group_id = 'admin'
    if request:
        request_path = request.path
    db.eventlog.add(msg, username, group_id,
                    _get_client_address(), is_important, request_path)

def _error_internal(msg=None, errcode=402):
    """ Error handler: Internal """
    _event_log("Internal error: %s" % msg, is_important=True)
    flash("Internal error: %s" % msg, 'danger')
    return render_template('error.html'), errcode

def _error_permission_denied(msg=None):
    """ Error handler: Permission Denied """
    _event_log("Permission denied: %s" % msg, is_important=True)
    flash("Permission denied: %s" % msg, 'danger')
    return render_template('error.html'), 401

def _get_chart_labels_months():
    """ Gets the chart labels """
    now = datetime.date.today()
    labels = []
    offset = 0
    for i in range(0, 12):
        if now.month - i == 0:
            offset = 1
        labels.append(calendar.month_name[now.month - i - offset])
    return labels

def _get_chart_labels_days():
    """ Gets the chart labels """
    now = datetime.date.today()
    labels = []
    for i in range(0, 30):
        then = now - datetime.timedelta(i)
        labels.append("%02i-%02i-%02i" % (then.year, then.month, then.day))
    return labels

def _get_chart_labels_hours():
    """ Gets the chart labels """
    labels = []
    for i in range(0, 24):
        labels.append("%02i" % i)
    return labels

def _validate_guid(guid):
    """ Validates if the string is a valid GUID """
    split = guid.split('-')
    if len(split) != 5:
        return False
    if len(split[0]) != 8:
        return False
    if len(split[1]) != 4:
        return False
    if len(split[2]) != 4:
        return False
    if len(split[3]) != 4:
        return False
    if len(split[4]) != 12:
        return False
    return True
