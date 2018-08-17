#!/usr/bin/python2
# -*- coding: utf-8 -*-
#
# Copyright (C) 2015 Richard Hughes <richard@hughsie.com>
# Licensed under the GNU General Public License Version 2
#
# pylint: disable=wrong-import-position

from __future__ import print_function

import os
import json
import calendar
import datetime
import string
import random

from glob import fnmatch

from flask import request, flash, render_template, g, Response

import gi
gi.require_version('GCab', '1.0')
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

def _get_dirname_safe(fn):
    """ gets the file dirname, also with win32-style backslashes """
    return os.path.dirname(fn.replace('\\', '/'))

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
    user_id = 2 	# Anonymous User
    vendor_id = 1	# admin
    request_path = None
    if hasattr(g, 'user') and g.user:
        user_id = g.user.user_id
        vendor_id = g.user.vendor_id
    if request:
        request_path = request.path
    from .models import Event
    from app import db
    event = Event(user_id=user_id,
                  message=msg,
                  vendor_id=vendor_id,
                  address=_get_client_address(),
                  request=request_path,
                  is_important=is_important)
    db.session.add(event)
    db.session.commit()

def _error_internal(msg=None, errcode=402):
    """ Error handler: Internal """
    flash("Internal error: %s" % msg, 'danger')
    return render_template('error.html'), errcode

def _error_permission_denied(msg=None):
    """ Error handler: Permission Denied """
    flash("Permission denied: %s" % msg, 'danger')
    return render_template('error.html'), 401

def _json_success(msg=None, uri=None, errcode=200):
    """ Success handler: JSON output """
    item = {}
    item['success'] = True
    if msg:
        item['msg'] = msg
    if uri:
        item['uri'] = uri
    dat = json.dumps(item, sort_keys=True, indent=4, separators=(',', ': '))
    return Response(response=dat,
                    status=errcode, \
                    mimetype="application/json")

def _json_error(msg=None, errcode=400):
    """ Error handler: JSON output """
    item = {}
    item['success'] = False
    if msg:
        item['msg'] = str(msg)
    dat = json.dumps(item, sort_keys=True, indent=4, separators=(',', ': '))
    return Response(response=dat,
                    status=errcode, \
                    mimetype="application/json")

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

def _get_chart_labels_days(limit=30):
    """ Gets the chart labels """
    now = datetime.date.today()
    labels = []
    for i in range(0, limit):
        then = now - datetime.timedelta(i)
        labels.append("%02i-%02i-%02i" % (then.year, then.month, then.day))
    return labels

def _get_chart_labels_hours():
    """ Gets the chart labels """
    labels = []
    for i in range(0, 24):
        labels.append("%02i" % i)
    return labels

def _email_check(value):
    """ Do a quick and dirty check on the email address """
    if len(value) < 5 or value.find('@') == -1 or value.find('.') == -1:
        return False
    return True

def _generate_password(size=10, chars=string.ascii_letters + string.digits):
    return ''.join(random.choice(chars) for _ in range(size))
