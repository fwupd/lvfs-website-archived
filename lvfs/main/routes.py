#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2015-2018 Richard Hughes <richard@hughsie.com>
#
# SPDX-License-Identifier: GPL-2.0+
#
# pylint: disable=wrong-import-position,singleton-comparison

import os
import html
import datetime
import fnmatch
import humanize
import iso3166

from flask import Blueprint, request, flash, url_for, redirect, render_template
from flask import send_from_directory, abort, Response, g
from flask_login import login_required, login_user, logout_user
from sqlalchemy.orm import joinedload

import GeoIP

from pkgversion import vercmp

from lvfs import app, db, lm, ploader, csrf

from lvfs.dbutils import _execute_count_star
from lvfs.pluginloader import PluginError

from lvfs.models import Firmware, Requirement, Vendor
from lvfs.models import User, Client, Event, AnalyticVendor, Remote
from lvfs.models import _get_datestr_from_datetime
from lvfs.hash import _addr_hash
from lvfs.util import _get_client_address, _get_settings, _xml_from_markdown, _get_chart_labels_days
from lvfs.util import _event_log, _error_internal

bp_main = Blueprint('main', __name__, template_folder='templates')

def _user_agent_safe_for_requirement(user_agent):

    # very early versions of fwupd used 'fwupdmgr' as the user agent
    if user_agent == 'fwupdmgr':
        return False

    # gnome-software/3.26.5 (Linux x86_64 4.14.0) fwupd/1.0.4
    sections = user_agent.split(' ')
    for chunk in sections:
        toks = chunk.split('/')
        if len(toks) == 2 and toks[0] == 'fwupd':
            return vercmp(toks[1], '0.8.0') >= 0

    # this is a heuristic; the logic is that it's unlikely that a distro would
    # ship a very new gnome-software and a very old fwupd
    for chunk in sections:
        toks = chunk.split('/')
        if len(toks) == 2 and toks[0] == 'gnome-software':
            return vercmp(toks[1], '3.26.0') >= 0

    # is is probably okay
    return True

@bp_main.route('/<path:resource>')
def serveStaticResource(resource):
    """ Return a static image or resource """

    # ban the robots that ignore robots.txt
    user_agent = request.headers.get('User-Agent')
    if user_agent:
        if user_agent.find('MJ12BOT') != -1:
            abort(403)
        if user_agent.find('ltx71') != -1:
            abort(403)
        if user_agent.find('Sogou') != -1:
            abort(403)

    # log certain kinds of files
    if resource.endswith('.cab'):

        # increment the firmware download counter
        fw = db.session.query(Firmware).\
                filter(Firmware.filename == os.path.basename(resource)).\
                options(joinedload('limits')).\
                options(joinedload('vendor')).first()
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

        # check the firmware vendor has no country block
        if fw.banned_country_codes:
            banned_country_codes = fw.banned_country_codes.split(',')
            geo = GeoIP.new(GeoIP.GEOIP_MEMORY_CACHE)
            country_code = geo.country_code_by_addr(_get_client_address())
            if country_code and country_code in banned_country_codes:
                return Response(response='firmware not available from this IP range',
                                status=451,
                                mimetype="text/plain")

        # check any firmware download limits
        for fl in fw.limits:
            if not fl.user_agent_glob or fnmatch.fnmatch(user_agent, fl.user_agent_glob):
                datestr = _get_datestr_from_datetime(datetime.date.today() - datetime.timedelta(1))
                cnt = _execute_count_star(db.session.query(Client).\
                            filter(Client.firmware_id == fw.firmware_id).\
                            filter(Client.datestr >= datestr))
                if cnt >= fl.value:
                    response = fl.response
                    if not response:
                        response = 'Too Many Requests'
                    resp = Response(response=response,
                                    status=429,
                                    mimetype='text/plain')
                    resp.headers['Retry-After'] = '86400'
                    return resp

        # this is cached for easy access on the firmware details page
        if not fw.do_not_track:
            fw.download_cnt += 1

        # log the client request
        if not fw.do_not_track:
            db.session.add(Client(addr=_addr_hash(_get_client_address()),
                                  firmware_id=fw.firmware_id,
                                  user_agent=user_agent))
            db.session.commit()

    # firmware blobs
    if resource.startswith('downloads/'):
        return send_from_directory(app.config['DOWNLOAD_DIR'], os.path.basename(resource))
    if resource.startswith('deleted/'):
        return send_from_directory(app.config['RESTORE_DIR'], os.path.basename(resource))
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

    def format_humanize_naturalday(tmp):
        if not tmp:
            return 'n/a'
        return humanize.naturalday(tmp)

    def format_humanize_naturaltime(tmp):
        if not tmp:
            return 'n/a'
        return humanize.naturaltime(tmp.replace(tzinfo=None))

    def format_humanize_intchar(tmp):
        if tmp > 1000000:
            return '%.0fM' % (float(tmp) / 1000000)
        if tmp > 1000:
            return '%.0fK' % (float(tmp) / 1000)
        return tmp

    def format_timedelta_approx(tmp):
        return humanize.naturaltime(tmp).replace(' from now', '')

    def format_size(num, suffix='B'):
        if not isinstance(num, int) and not isinstance(num, int):
            return "???%s???" % num
        for unit in ['', 'Ki', 'Mi', 'Gi', 'Ti', 'Pi', 'Ei', 'Zi']:
            if abs(num) < 1024.0:
                return "%3.1f%s%s" % (num, unit, suffix)
            num /= 1024.0
        return "%.1f%s%s" % (num, 'Yi', suffix)

    def format_iso3166(tmp):
        return iso3166.countries.get(tmp, ['Unknown!'])[0]

    def format_plugin_id(tmp):
        return ploader.get_by_id(tmp)

    def format_html_from_markdown(tmp):
        if not tmp:
            return '<p>None</p>'
        root = _xml_from_markdown(tmp)
        txt = ''
        for n in root:
            if n.tag == 'p':
                txt += '<p>' + html.escape(n.text) + '</p>'
            elif n.tag == 'ul' or n.tag == 'ol':
                txt += '<ul>'
                for c in n:
                    if c.tag == 'li':
                        txt += '<li>' + html.escape(c.text) + '</li>'
                txt += '</ul>'
        return txt

    return dict(format_size=format_size,
                format_humanize_naturalday=format_humanize_naturalday,
                format_humanize_naturaltime=format_humanize_naturaltime,
                format_humanize_intchar=format_humanize_intchar,
                format_timedelta_approx=format_timedelta_approx,
                format_html_from_markdown=format_html_from_markdown,
                format_timestamp=format_timestamp,
                format_iso3166=format_iso3166,
                format_plugin_id=format_plugin_id,
                loader_plugins=sorted(ploader.get_all(), key=lambda x: x.name))

@lm.unauthorized_handler
def unauthorized():
    msg = ''
    if request.url:
        msg += 'Tried to request %s' % request.url
    if request.user_agent:
        msg += ' from %s' % request.user_agent
    flash('Permission denied: {}'.format(msg), 'danger')
    return redirect(url_for('main.route_index'))

@app.errorhandler(401)
def errorhandler_401(msg=None):
    return render_template('error-401.html', msg=msg), 401

@bp_main.route('/')
@bp_main.route('/lvfs/')
def route_index():
    vendors_logo = db.session.query(Vendor).\
                            filter(Vendor.visible_on_landing).\
                            order_by(Vendor.display_name).limit(10).all()
    vendors_quote = db.session.query(Vendor).\
                            filter(Vendor.quote_text != None).\
                            filter(Vendor.quote_text != '').\
                            order_by(Vendor.display_name).limit(10).all()
    return render_template('index.html',
                           vendors_logo=vendors_logo,
                           vendors_quote=vendors_quote)

@bp_main.route('/lvfs/dashboard')
@login_required
def route_dashboard():
    user = db.session.query(User).filter(User.username == 'sign-test@fwupd.org').first()
    settings = _get_settings()
    default_admin_password = False
    if user and user.verify_password('Pa$$w0rd'):
        default_admin_password = True

    # get the 10 most recent firmwares
    fws = db.session.query(Firmware).\
                filter(Firmware.user_id == g.user.user_id).\
                join(Remote).filter(Remote.name != 'deleted').\
                order_by(Firmware.timestamp.desc()).limit(10).all()

    download_cnt = 0
    devices_cnt = 0
    appstream_ids = {}
    for fw in g.user.vendor.fws:
        download_cnt += fw.download_cnt
        for md in fw.mds:
            appstream_ids[md.appstream_id] = fw
    devices_cnt = len(appstream_ids)

    # this is somewhat klunky
    data = []
    datestr = _get_datestr_from_datetime(datetime.date.today() - datetime.timedelta(days=31))
    for cnt in db.session.query(AnalyticVendor.cnt).\
                    filter(AnalyticVendor.vendor_id == g.user.vendor.vendor_id).\
                    filter(AnalyticVendor.datestr > datestr).\
                    order_by(AnalyticVendor.datestr):
        data.append(int(cnt[0]))

    return render_template('dashboard.html',
                           fws_recent=fws,
                           devices_cnt=devices_cnt,
                           download_cnt=download_cnt,
                           labels_days=_get_chart_labels_days(limit=len(data))[::-1],
                           data_days=data,
                           server_warning=settings.get('server_warning', None),
                           category='home',
                           default_admin_password=default_admin_password)

@bp_main.route('/lvfs/newaccount')
def route_new_account():
    """ New account page for prospective vendors """
    return redirect('https://lvfs.readthedocs.io/en/latest/apply.html', code=302)

def _create_user_for_oauth_username(username):
    """ If any oauth wildcard match, create a *un-committed* User object """

    # does this username match any globs specified by the vendor
    for v in db.session.query(Vendor).filter(Vendor.oauth_domain_glob != None): # pylint: disable=singleton-comparison
        for glob in v.oauth_domain_glob.split(','):
            if not fnmatch.fnmatch(username.lower(), glob):
                continue
            if v.oauth_unknown_user == 'create':
                return User(username, vendor_id=v.vendor_id, auth_type='oauth')
            if v.oauth_unknown_user == 'disabled':
                return User(username, vendor_id=v.vendor_id)
    return None

# unauthenticed
@bp_main.route('/lvfs/login1')
def route_login1():
    if hasattr(g, 'user') and g.user:
        flash('You are already logged in', 'warning')
        return redirect(url_for('main.route_dashboard'))
    return render_template('login1.html')

# unauthenticed
@bp_main.route('/lvfs/login1', methods=['POST'])
def route_login1_response():
    if 'username' not in request.form:
        flash('Username not specified', 'warning')
        return redirect(url_for('main.route_login1'))
    user = db.session.query(User).filter(User.username == request.form['username']).first()
    if not user:
        flash('Failed to log in: Incorrect username %s' % request.form['username'], 'danger')
        return redirect(url_for('main.route_login1'))
    return render_template('login2.html', u=user)

@bp_main.route('/lvfs/login', methods=['POST'])
@csrf.exempt
def route_login():
    """ A login screen to allow access to the LVFS main page """
    # auth check
    user = db.session.query(User).filter(User.username == request.form['username']).first()
    if user:
        if user.auth_type == 'oauth':
            flash('Failed to log in as %s: Only OAuth can be used for this user' % user.username, 'danger')
            return redirect(url_for('main.route_index'))
        if not user.verify_password(request.form['password']):
            flash('Failed to log in: Incorrect password for %s' % request.form['username'], 'danger')
            return redirect(url_for('main.route_login1'))
    else:
        # check OAuth, user is NOT added to the database
        user = _create_user_for_oauth_username(request.form['username'])
        if not user:
            flash('Failed to log in: Incorrect username %s' % request.form['username'], 'danger')
            return redirect(url_for('main.route_index'))

    # check auth type
    if not user.auth_type or user.auth_type == 'disabled':
        if user.dtime:
            flash('Failed to log in as %s: User account was disabled on %s' %
                  (request.form['username'], user.dtime.strftime('%Y-%m-%d')), 'danger')
        else:
            flash('Failed to log in as %s: User account is disabled' % request.form['username'], 'danger')
        return redirect(url_for('main.route_index'))

    # check OTP
    if user.is_otp_enabled:
        if 'otp' not in request.form or not request.form['otp']:
            flash('Failed to log in: 2FA OTP required', 'danger')
            return redirect(url_for('main.route_login1'))
        if not user.verify_totp(request.form['otp']):
            flash('Failed to log in: Incorrect 2FA OTP', 'danger')
            return redirect(url_for('main.route_login1'))

    # success
    login_user(user, remember=False)
    g.user = user
    if user.password_ts:
        flash('Logged in', 'info')
    else:
        flash('Logged in, now change your password using Profile ⇒ User', 'info')

    # set the access time
    user.atime = datetime.datetime.utcnow()
    db.session.commit()

    return redirect(url_for('main.route_dashboard'))

@bp_main.route('/lvfs/login/<plugin_id>')
def route_login_oauth(plugin_id):

    # find the plugin that can authenticate us
    p = ploader.get_by_id(plugin_id)
    if not p:
        return _error_internal('no plugin {}'.format(plugin_id))
    if not p.oauth_authorize:
        return _error_internal('no oauth support in plugin {}'.format(plugin_id))
    try:
        return p.oauth_authorize(url_for('main.route_login_oauth_authorized', plugin_id=plugin_id, _external=True))
    except PluginError as e:
        return _error_internal(str(e))

@bp_main.route('/lvfs/login/authorized/<plugin_id>')
def route_login_oauth_authorized(plugin_id):

    # find the plugin that can authenticate us
    p = ploader.get_by_id(plugin_id)
    if not p:
        _error_internal('no plugin {}'.format(plugin_id))
    if not hasattr(p, 'oauth_get_data'):
        return _error_internal('no oauth support in plugin {}'.format(plugin_id))
    try:
        data = p.oauth_get_data()
        if 'userPrincipalName' not in data:
            return _error_internal('No userPrincipalName in profile')
    except PluginError as e:
        return _error_internal(str(e))

    # auth check
    created_account = False
    user = db.session.query(User).filter(User.username == data['userPrincipalName']).first()
    if not user:
        user = _create_user_for_oauth_username(data['userPrincipalName'])
        if user:
            db.session.add(user)
            db.session.commit()
            _event_log('Auto created user of type %s for vendor %s' % (user.auth_type, user.vendor.group_id))
            created_account = True
    if not user:
        flash('Failed to log in: no user for %s' % data['userPrincipalName'], 'danger')
        return redirect(url_for('main.route_index'))
    if not user.auth_type:
        flash('Failed to log in: User account %s is disabled' % user.username, 'danger')
        return redirect(url_for('main.route_index'))
    if user.auth_type != 'oauth':
        flash('Failed to log in: Only some accounts can log in using OAuth', 'danger')
        return redirect(url_for('main.route_index'))

    # sync the display name
    if 'displayName' in data:
        if user.display_name != data['displayName']:
            user.display_name = data['displayName']
            db.session.commit()

    # success
    login_user(user, remember=False)
    g.user = user
    if created_account:
        flash('Logged in, and created account', 'info')
    else:
        flash('Logged in', 'info')

    # set the access time
    user.atime = datetime.datetime.utcnow()
    db.session.commit()

    return redirect(url_for('main.route_dashboard'))

@bp_main.route('/lvfs/logout')
@login_required
def route_logout():
    flash('Logged out from %s' % g.user.username, 'info')
    ploader.oauth_logout()
    logout_user()
    return redirect(url_for('main.route_index'))

@bp_main.route('/lvfs/eventlog')
@bp_main.route('/lvfs/eventlog/<int:start>')
@bp_main.route('/lvfs/eventlog/<int:start>/<int:length>')
@login_required
def route_eventlog(start=0, length=20):
    """
    Show an event log of user actions.
    """
    # security check
    if not g.user.check_acl('@view-eventlog'):
        flash('Permission denied: Unable to show event log for non-QA user', 'danger')
        return redirect(url_for('main.route_dashboard'))

    # get the page selection correct
    if g.user.check_acl('@admin'):
        eventlog_len = _execute_count_star(db.session.query(Event))
    else:
        eventlog_len = _execute_count_star(db.session.query(Event).\
                            filter(Event.vendor_id == g.user.vendor_id))

    # limit this to keep the UI sane
    if eventlog_len / length > 20:
        eventlog_len = length * 20

    # table contents
    if g.user.check_acl('@admin'):
        events = db.session.query(Event).\
                        order_by(Event.id.desc()).\
                        offset(start).limit(length).all()
    else:
        events = db.session.query(Event).\
                        filter(Event.vendor_id == g.user.vendor_id).\
                        order_by(Event.id.desc()).\
                        offset(start).limit(length).all()
    return render_template('eventlog.html', events=events,
                           category='home',
                           start=start,
                           page_length=length,
                           total_length=eventlog_len)

@bp_main.route('/lvfs/profile')
@login_required
def route_profile():
    """
    Allows the normal user to change details about the account,
    """

    # security check
    if not g.user.check_acl('@view-profile'):
        flash('Permission denied: Unable to view profile as account locked', 'danger')
        return redirect(url_for('main.route_dashboard'))
    return render_template('profile.html', u=g.user)

# old names used on the static site
@bp_main.route('/users.html')
def route_users_html():
    return redirect(url_for('docs.route_users'), code=302)
@bp_main.route('/vendors.html')
def route_vendors_html():
    return redirect(url_for('docs.route_vendors'), code=302)
@bp_main.route('/developers.html')
def route_developers_html():
    return redirect(url_for('docs.route_developers'), code=302)
@bp_main.route('/index.html')
def route_index_html():
    return redirect(url_for('main.route_index'), code=302)
@bp_main.route('/lvfs/devicelist')
def route_devicelist():
    return redirect(url_for('devices.route_list'), code=302)
@bp_main.route('/status')
@bp_main.route('/vendorlist') # deprecated
@bp_main.route('/lvfs/vendorlist')
def route_vendorlist():
    return redirect(url_for('vendors.route_list'), code=302)
