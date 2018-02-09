#!/usr/bin/python2
# -*- coding: utf-8 -*-
#
# Copyright (C) 2015 Richard Hughes <richard@hughsie.com>
# Licensed under the GNU General Public License Version 2

from __future__ import print_function

import os
import calendar
import datetime
from glob import fnmatch

from flask import request, flash, render_template, g

from gi.repository import GCab
from gi.repository import GLib

def _get_settings(unused_prefix=None):
    """ return a dict of all the settings """
    from app import db
    from .models import Setting
    settings = {}
    for setting in db.session.query(Setting).all():
        settings[setting.key] = setting.value
    return settings

def _get_basename_safe(fn):
    """ gets the file basename, also with win32-style backslashes """
    return os.path.basename(fn.replace('\\', '/'))

def _archive_get_files_from_glob(arc, glob):
    arr = []
    for cffolder in arc.get_folders():
        for cffile in cffolder.get_files():
            filename = cffile.get_name().replace('\\', '/')
            if fnmatch.fnmatch(filename, glob):
                arr.append(cffile)
    return arr

def _archive_add(arc, filename, contents):
    cffile = GCab.File.new_with_bytes(filename, GLib.Bytes.new(contents))
    cffolders = arc.get_folders()
    if not cffolders:
        cffolders = [GCab.Folder.new(GCab.Compression.NONE)]
        arc.add_folder(cffolders[0])
    cffolders[0].add_file(cffile, False)

def _get_client_address():
    """ Gets user IP address """
    if request.headers.getlist("X-Forwarded-For"):
        return request.headers.getlist("X-Forwarded-For")[0]
    if not request.remote_addr:
        return '127.0.0.1'
    return request.remote_addr

def _event_log(msg, is_important=False):
    """ Adds an item to the event log """
    username = 'anonymous'
    group_id = 'admin'
    request_path = None
    if hasattr(g, 'user'):
        username = g.user.username
        group_id = g.user.group_id
    if request:
        request_path = request.path
    from .models import EventLogItem
    from app import db
    event = EventLogItem(username=username,
                         message=msg,
                         group_id=group_id,
                         address=_get_client_address(),
                         request=request_path,
                         is_important=is_important)
    db.session.add(event)
    db.session.commit()

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
