#!/usr/bin/python2
# -*- coding: utf-8 -*-
#
# Copyright (C) 2015-2018 Richard Hughes <richard@hughsie.com>
# Licensed under the GNU General Public License Version 2

from __future__ import print_function

import os
import datetime
import math

from flask import session, request, flash, url_for, redirect, render_template
from flask import send_from_directory, abort, g
from flask_login import login_required, login_user, logout_user

from app import app, db, lm
from .db import _execute_count_star

from .models import Firmware, DownloadKind, UserCapability
from .models import User, Analytic, Client, EventLogItem
from .hash import _qa_hash, _password_hash, _addr_hash
from .util import _event_log, _get_client_address, _get_settings
from .util import _error_internal, _error_permission_denied

@app.route('/<path:resource>')
def serveStaticResource(resource):
    """ Return a static image or resource """

    # ban the robots that ignore robots.txt
    user_agent = request.headers.get('User-Agent')
    if user_agent:
        if user_agent.find('MJ12BOT') != -1:
            abort(403)
        if user_agent.find('ltx71') != -1:
            abort(403)

    # log certain kinds of files
    if resource.endswith('.cab'):

        # increment the firmware download counter
        fw = db.session.query(Firmware).\
                filter(Firmware.filename == os.path.basename(resource)).first()
        if not fw:
            abort(404)
        fw.download_cnt += 1

        # either update the analytics counter, or create one for that day
        analytic_tmp = Analytic(DownloadKind.FIRMWARE)
        analytic = db.session.query(Analytic).\
                        filter(Analytic.kind == analytic_tmp.kind).\
                        filter(Analytic.datestr == analytic_tmp.datestr).\
                        first()
        if analytic:
            analytic.cnt += 1
        else:
            db.session.add(analytic_tmp)

        # log the client request
        db.session.add(Client(addr=_addr_hash(_get_client_address()),
                              filename=fw.filename,
                              user_agent=user_agent))
        db.session.commit()

    # firmware blobs
    if resource.startswith('downloads/'):
        return send_from_directory(app.config['DOWNLOAD_DIR'], os.path.basename(resource))

    # static files served locally
    return send_from_directory(os.path.join(app.root_path, 'static'), resource)

@app.context_processor
def utility_processor():

    def format_truncate(tmp, length):
        if len(tmp) <= length:
            return tmp
        return tmp[:length] + u'…'

    def format_timestamp(tmp):
        if not tmp:
            return 'n/a'
        return datetime.datetime.fromtimestamp(tmp).strftime('%Y-%m-%d %H:%M:%S')

    def format_size(num, suffix='B'):
        if not isinstance(num, int) and not isinstance(num, long):
            return "???%s???" % num
        for unit in ['', 'Ki', 'Mi', 'Gi', 'Ti', 'Pi', 'Ei', 'Zi']:
            if abs(num) < 1024.0:
                return "%3.1f%s%s" % (num, unit, suffix)
            num /= 1024.0
        return "%.1f%s%s" % (num, 'Yi', suffix)

    def format_qa_hash(tmp):
        return _qa_hash(tmp)

    return dict(format_size=format_size,
                format_truncate=format_truncate,
                format_qa_hash=format_qa_hash,
                format_timestamp=format_timestamp)

@lm.unauthorized_handler
def unauthorized():
    msg = ''
    if request.url:
        msg += 'Tried to request %s' % request.url
    if request.user_agent:
        msg += ' from %s' % request.user_agent
    return _error_permission_denied(msg)

@app.errorhandler(401)
def errorhandler_401(msg=None):
    print("generic error handler")
    return _error_permission_denied(msg)

@app.route('/developers')
def developers():
    return render_template('developers.html')

@app.route('/privacy')
def privacy():
    return render_template('privacy.html')

@app.route('/users')
def users():
    return render_template('users.html')

@app.route('/donations')
def donations():
    return render_template('donations.html')

@app.route('/vendors')
def vendors():
    return render_template('vendors.html')

@app.route('/')
@app.route('/lvfs/')
def index():
    user = db.session.query(User).filter(User.username == 'admin').first()
    settings = _get_settings()
    default_admin_password = False
    if user and user.password == '5459dbe5e9aa80e077bfa40f3fb2ca8368ed09b4':
        default_admin_password = True
    server_warning = ''
    if 'server_warning' in settings:
        server_warning = settings['server_warning']
    return render_template('index.html',
                           server_warning=server_warning,
                           default_admin_password=default_admin_password)

@app.route('/lvfs/newaccount')
def new_account():
    """ New account page for prospective vendors """
    return render_template('new-account.html')

@app.route('/lvfs/login', methods=['POST'])
def login():
    """ A login screen to allow access to the LVFS main page """
    # auth check
    user = db.session.query(User).\
            filter(User.username == request.form['username']).\
            filter(User.password == _password_hash(request.form['password'])).first()
    if not user:
        # log failure
        _event_log('Failed login attempt for %s' % request.form['username'])
        flash('Incorrect username or password', 'danger')
        return redirect(url_for('.index'))
    if not user.is_enabled:
        # log failure
        _event_log('Failed login attempt for %s (user disabled)' % request.form['username'])
        flash('User account is disabled', 'danger')
        return redirect(url_for('.index'))

    # this is signed, not encrypted
    session['username'] = user.username
    login_user(user, remember=False)
    g.user = user

    # log success
    _event_log('Logged on')
    return redirect(url_for('.index'))

@app.route('/lvfs/logout')
def logout():
    # remove the username from the session
    session.pop('username', None)
    logout_user()
    return redirect(url_for('.index'))

@app.route('/lvfs/eventlog')
@app.route('/lvfs/eventlog/<start>')
@app.route('/lvfs/eventlog/<start>/<length>')
@login_required
def eventlog(start=0, length=20):
    """
    Show an event log of user actions.
    """
    # security check
    if not g.user.check_capability(UserCapability.QA):
        return _error_permission_denied('Unable to show event log for non-QA user')

    # get the page selection correct
    if g.user.check_capability('admin'):
        eventlog_len = _execute_count_star(db.session.query(EventLogItem))
    else:
        eventlog_len = _execute_count_star(db.session.query(EventLogItem).\
                            filter(EventLogItem.group_id == g.user.group_id))
    nr_pages = int(math.ceil(eventlog_len / float(length)))

    # table contents
    if g.user.check_capability(UserCapability.Admin):
        events = db.session.query(EventLogItem).\
                        order_by(EventLogItem.id.desc()).\
                        offset(start).limit(length).all()
    else:
        events = db.session.query(EventLogItem).\
                        filter(EventLogItem.group_id == g.user.group_id).\
                        order_by(EventLogItem.id.desc()).\
                        offset(start).limit(length).all()
    if len(events) == 0:
        return _error_internal('No event log available!')

    # limit this to keep the UI sane
    if nr_pages > 20:
        nr_pages = 20

    html = ''
    for i in range(nr_pages):
        if int(start) == i * int(length):
            html += '%i ' % (i + 1)
        else:
            html += '<a href="/lvfs/eventlog/%i/%s">%i</a> ' % (i * int(length), int(length), i + 1)
    return render_template('eventlog.html', events=events, pagination_footer=html)

@app.route('/lvfs/profile')
@login_required
def profile():
    """
    Allows the normal user to change details about the account,
    """

    # security check
    if not g.user.check_capability(UserCapability.User):
        return _error_permission_denied('Unable to view profile as account locked')

    return render_template('profile.html',
                           vendor_name=g.user.display_name,
                           contact_email=g.user.email)
