#!/usr/bin/python2
# -*- coding: utf-8 -*-
#
# Copyright (C) 2015-2018 Richard Hughes <richard@hughsie.com>
# Licensed under the GNU General Public License Version 2

from __future__ import print_function

import os
import datetime
import humanize

from flask import request, flash, url_for, redirect, render_template
from flask import send_from_directory, abort, Response, g
from flask_login import login_required, login_user, logout_user

from gi.repository import AppStreamGlib

from app import app, db, lm, ploader
from .dbutils import _execute_count_star
from .pluginloader import PluginError

from .models import Firmware, DownloadKind, UserCapability, Requirement, Component
from .models import User, Analytic, Client, Event, Useragent, _get_datestr_from_datetime
from .hash import _qa_hash, _password_hash, _addr_hash
from .util import _get_client_address, _get_settings
from .util import _error_permission_denied, _event_log

def _user_agent_safe_for_requirement(user_agent):

    # very early versions of fwupd used 'fwupdmgr' as the user agent
    if user_agent == 'fwupdmgr':
        return False

    # gnome-software/3.26.5 (Linux x86_64 4.14.0) fwupd/1.0.4
    sections = user_agent.split(' ')
    for chunk in sections:
        toks = chunk.split('/')
        if len(toks) == 2 and toks[0] == 'fwupd':
            return AppStreamGlib.utils_vercmp(toks[1], '0.8.0') >= 0

    # this is a heuristic; the logic is that it's unlikely that a distro would
    # ship a very new gnome-software and a very old fwupd
    for chunk in sections:
        toks = chunk.split('/')
        if len(toks) == 2 and toks[0] == 'gnome-software':
            return AppStreamGlib.utils_vercmp(toks[1], '3.26.0') >= 0

    # is is probably okay
    return True

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

        # check the user agent isn't in the blocklist for this firmware
        for md in fw.mds:
            req = db.session.query(Requirement).\
                            filter(Requirement.component_id == md.component_id).\
                            filter(Requirement.kind == 'id').\
                            filter(Requirement.value == 'org.freedesktop.fwupd').\
                            first()
            if req and user_agent and not _user_agent_safe_for_requirement(user_agent):
                return Response(response='detected fwupd version too old',
                                status=412,
                                mimetype="text/plain")

        # this is cached for easy access on the firmware details page
        fw.download_cnt += 1

        # either update the analytics counter, or create one for that day
        datestr = _get_datestr_from_datetime(datetime.date.today())
        analytic = db.session.query(Analytic).\
                        filter(Analytic.kind == DownloadKind.FIRMWARE).\
                        filter(Analytic.datestr == datestr).\
                        first()
        if analytic:
            analytic.cnt += 1
        else:
            db.session.add(Analytic(DownloadKind.FIRMWARE, datestr))

        # update the user-agent counter
        if user_agent:
            user_agent_safe = user_agent.split(' ')[0]
            ug = db.session.query(Useragent).\
                            filter(Useragent.value == user_agent_safe).\
                            filter(Useragent.datestr == datestr).\
                            first()
            if ug:
                ug.cnt += 1
            else:
                db.session.add(Useragent(user_agent_safe, datestr))

        # log the client request
        db.session.add(Client(addr=_addr_hash(_get_client_address()),
                              firmware_id=fw.firmware_id,
                              user_agent=user_agent))
        db.session.commit()

    # firmware blobs
    if resource.startswith('downloads/'):
        return send_from_directory(app.config['DOWNLOAD_DIR'], os.path.basename(resource))
    if resource.startswith('uploads/'):
        return send_from_directory(app.config['UPLOAD_DIR'], os.path.basename(resource))

    # static files served locally
    return send_from_directory(os.path.join(app.root_path, 'static'), resource)

@app.context_processor
def utility_processor():

    def format_timestamp(tmp):
        if not tmp:
            return 'n/a'
        return datetime.datetime.fromtimestamp(tmp).strftime('%Y-%m-%d %H:%M:%S')

    def format_timedelta_approx(tmp):
        return humanize.naturaltime(tmp)

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
                format_qa_hash=format_qa_hash,
                format_timedelta_approx=format_timedelta_approx,
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
    return render_template('vendors.html',
                           firmware_cnt=db.session.query(Firmware).count(),
                           devices_cnt=db.session.query(Component.appstream_id).distinct().count())

@app.route('/metainfo')
def metainfo():
    return render_template('metainfo.html')

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
    used_deprecated_username = False
    user = db.session.query(User).\
            filter(User.username == request.form['username']).\
            filter(User.password == _password_hash(request.form['password'])).first()
    if not user:
        # fallback, but not forever
        user = db.session.query(User).\
                filter(User.username_old == request.form['username']).\
                filter(User.password == _password_hash(request.form['password'])).first()
        used_deprecated_username = True
    if not user:
        flash('Failed to log in: Incorrect username or password for %s' % request.form['username'], 'danger')
        return redirect(url_for('.index'))
    if not user.auth_type:
        flash('Failed to log in: User account %s is disabled' % request.form['username'], 'danger')
        return redirect(url_for('.index'))
    if user.auth_type == 'oauth':
        flash('Failed to log in: Only OAuth can be used to log in for this user', 'danger')
        return redirect(url_for('.index'))

    # success
    login_user(user, remember=False)
    g.user = user
    if used_deprecated_username:
        # show the user something to remind them
        flash(u'Logged in — but from 1st September 2018 you will be required to '
              'use %s instead of %s.' % (user.username, user.username_old), 'warning')
    else:
        flash('Logged in', 'info')
    return redirect(url_for('.index'))

@app.route('/lvfs/login/<plugin_id>')
def login_oauth(plugin_id):

    # find the plugin that can authenticate us
    p = ploader.get_by_id(plugin_id)
    if not p:
        return _error_permission_denied('no plugin %s' % plugin_id)
    if not p.oauth_authorize:
        return _error_permission_denied('no oauth support in plugin %s' % plugin_id)
    try:
        _event_log('attempted to login using OAuth')
        return p.oauth_authorize(url_for('login_oauth_authorized', plugin_id=plugin_id, _external=True))
    except PluginError as e:
        return _error_permission_denied(str(e))

@app.route('/lvfs/login/authorized/<plugin_id>')
def login_oauth_authorized(plugin_id):

    # find the plugin that can authenticate us
    p = ploader.get_by_id(plugin_id)
    if not p:
        return _error_permission_denied('no plugin %s' % plugin_id)
    if not hasattr(p, 'oauth_get_data'):
        return _error_permission_denied('no oauth support in plugin %s' % plugin_id)
    try:
        data = p.oauth_get_data()
        _event_log('OAuth returned: %s' % str(data))
        if 'userPrincipalName' not in data:
            raise PluginError('No userPrincipalName in profile')
    except PluginError as e:
        return _error_permission_denied(str(e))

    # auth check
    user = db.session.query(User).filter(User.username == data['userPrincipalName']).first()
    if not user:
        flash('Failed to log in: no user for %s' % data['userPrincipalName'], 'danger')
        return redirect(url_for('.index'))
    if not user.auth_type:
        flash('Failed to log in: User account %s is disabled' % user.username, 'danger')
        return redirect(url_for('.index'))
    if user.auth_type != 'oauth':
        flash('Failed to log in: Only some accounts can log in using OAuth', 'danger')
        return redirect(url_for('.index'))
    if user.password:
        flash('Failed to log in: Only accounts with no local password can log in using OAuth', 'danger')
        return redirect(url_for('.index'))

    # sync the display name
    if 'displayName' in data:
        if user.display_name != data['displayName']:
            user.display_name = data['displayName']
            db.session.commit()

    # success
    login_user(user, remember=False)
    g.user = user
    flash('Logged in', 'info')
    return redirect(url_for('.index'))

@app.route('/lvfs/logout')
@login_required
def logout():
    flash('Logged out from %s' % g.user.username, 'info')
    ploader.oauth_logout()
    logout_user()
    return redirect(url_for('.index'))

@app.route('/lvfs/eventlog')
@app.route('/lvfs/eventlog/<int:start>')
@app.route('/lvfs/eventlog/<int:start>/<int:length>')
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
        eventlog_len = _execute_count_star(db.session.query(Event))
    else:
        eventlog_len = _execute_count_star(db.session.query(Event).\
                            filter(Event.vendor_id == g.user.vendor_id))

    # limit this to keep the UI sane
    if eventlog_len / length > 20:
        eventlog_len = length * 20

    # table contents
    if g.user.check_capability(UserCapability.Admin):
        events = db.session.query(Event).\
                        order_by(Event.id.desc()).\
                        offset(start).limit(length).all()
    else:
        events = db.session.query(Event).\
                        filter(Event.vendor_id == g.user.vendor_id).\
                        order_by(Event.id.desc()).\
                        offset(start).limit(length).all()
    return render_template('eventlog.html', events=events,
                           start=start, page_length=length, total_length=eventlog_len)

@app.route('/lvfs/profile')
@login_required
def profile():
    """
    Allows the normal user to change details about the account,
    """

    # security check
    if not g.user.check_capability(UserCapability.User):
        return _error_permission_denied('Unable to view profile as account locked')

    return render_template('profile.html')

# old names used on the static site
@app.route('/users.html')
def users_html():
    return redirect(url_for('.users'), code=302)
@app.route('/vendors.html')
def vendors_html():
    return redirect(url_for('.vendors'), code=302)
@app.route('/developers.html')
def developers_html():
    return redirect(url_for('.developers'), code=302)
@app.route('/index.html')
def index_html():
    return redirect(url_for('.index'), code=302)
