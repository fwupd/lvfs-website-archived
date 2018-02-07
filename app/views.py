#!/usr/bin/python2
# -*- coding: utf-8 -*-
#
# Copyright (C) 2015-2017 Richard Hughes <richard@hughsie.com>
# Licensed under the GNU General Public License Version 2

from __future__ import print_function

import os
import datetime
import hashlib
import math

from gi.repository import AppStreamGlib
from gi.repository import Gio

from flask import session, request, flash, url_for, redirect, render_template, Response
from flask import send_from_directory, abort, make_response, g
from flask_login import login_required, login_user, logout_user

from app import app, db, lm, ploader

from .models import Firmware, FirmwareMd, FirmwareRequirement, DownloadKind, UserCapability
from .uploadedfile import UploadedFile, FileTooLarge, FileTooSmall, FileNotSupported, MetadataInvalid
from .hash import _qa_hash, _password_hash
from .util import _event_log, _get_client_address
from .util import _error_internal, _error_permission_denied
from .util import _get_chart_labels_months, _get_chart_labels_days
from .metadata import _metadata_update_group, _metadata_update_targets, _metadata_update_pulp

################################################################################

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
        db.clients.add(datetime.date.today(), DownloadKind.FIRMWARE)
        db.clients.increment(_get_client_address(),
                             os.path.basename(resource),
                             user_agent)

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
    user = db.users.get_item('admin')
    settings = db.settings.get_all()
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

@login_required
@app.route('/lvfs/metadata/<qa_group>')
def metadata_remote(qa_group):
    """
    Generate a remote file for a given QA group.
    """

    # find the Group
    if not db.groups.get_item(qa_group):
        return _error_internal('No QA Group')

    # generate file
    remote = []
    remote.append('[fwupd Remote]')
    remote.append('Enabled=true')
    remote.append('Title=Embargoed for ' + qa_group)
    remote.append('Keyring=gpg')
    remote.append('MetadataURI=https://fwupd.org/downloads/firmware-' + _qa_hash(qa_group) + '.xml.gz')
    remote.append('OrderBefore=lvfs,fwupd')
    fn = qa_group + '-embargo.conf'
    response = make_response('\n'.join(remote))
    response.headers['Content-Disposition'] = 'attachment; filename=' + fn
    response.mimetype = 'text/plain'
    return response

@app.route('/lvfs/metadata')
@login_required
def metadata_view():
    """
    Show all metadata available to this user.
    """

    # show all embargo metadata URLs when admin user
    group_ids = []
    if g.user.check_capability('admin'):
        for group in db.groups.get_all():
            group_ids.append(group.group_id)
    else:
        group_ids.append(g.user.group_id)
    return render_template('metadata.html',
                           group_id=g.user.group_id,
                           group_ids=group_ids)

@app.route('/lvfs/upload', methods=['GET', 'POST'])
@login_required
def upload():
    """ Upload a .cab file to the LVFS service """

    # only accept form data
    if request.method != 'POST':
        if 'username' not in session:
            return redirect(url_for('.index'))
        vendor_ids = []
        grp = db.groups.get_item(g.user.group_id)
        if grp:
            vendor_ids.extend(grp.vendor_ids)
        return render_template('upload.html', vendor_ids=vendor_ids)

    # not correct parameters
    if not 'target' in request.form:
        return _error_internal('No target')
    if not 'file' in request.files:
        return _error_internal('No file')

    # can the user upload directly to stable
    if request.form['target'] in ['stable', 'testing']:
        if not g.user.check_capability(UserCapability.QA):
            return _error_permission_denied('Unable to upload to this target as not QA user')

    # load in the archive
    fileitem = request.files['file']
    if not fileitem:
        return _error_internal('No file object')
    try:
        ufile = UploadedFile(ploader)
        ufile.parse(os.path.basename(fileitem.filename), fileitem.read())
    except (FileTooLarge, FileTooSmall, FileNotSupported, MetadataInvalid) as e:
        flash(str(e), 'danger')
        return redirect(request.url)

    # check the file does not already exist
    fw = db.firmware.get_item(ufile.firmware_id)
    if fw:
        flash('A firmware file with hash %s already exists' % fw.firmware_id, 'danger')
        return redirect('/lvfs/firmware/%s' % fw.firmware_id)

    # check the guid and version does not already exist
    fws = db.firmware.get_all()
    for component in ufile.get_components():
        provides_value = component.get_provides()[0].get_value()
        release_default = component.get_release_default()
        release_version = release_default.get_version()
        for fw in fws:
            for md in fw.mds:
                for guid in md.guids:
                    if guid == provides_value and md.version == release_version:
                        flash('A firmware file for version %s already exists' % release_version, 'danger')
                        return redirect('/lvfs/firmware/%s' % fw.firmware_id)

    # check if the file dropped a GUID previously supported
    for component in ufile.get_components():
        new_guids = []
        for prov in component.get_provides():
            if prov.get_kind() != AppStreamGlib.ProvideKind.FIRMWARE_FLASHED:
                continue
            new_guids.append(prov.get_value())
        for fw in fws:
            for md in fw.mds:
                if md.cid != component.get_id():
                    continue
                for old_guid in md.guids:
                    if not old_guid in new_guids:
                        flash('Firmware %s dropped a GUID previously '
                              'supported %s' % (md.cid, old_guid), 'danger')
                        return redirect(request.url)

    # allow plugins to add files
    settings = db.settings.get_all()
    metadata = {}
    metadata['$DATE$'] = datetime.datetime.now().replace(microsecond=0).isoformat()
    metadata['$FWUPD_MIN_VERSION$'] = ufile.fwupd_min_version
    metadata['$CAB_FILENAME$'] = ufile.filename_new
    metadata['$FIRMWARE_BASEURI$'] = settings['firmware_baseuri']
    ploader.archive_finalize(ufile.get_repacked_cabinet(), metadata)

    # export the new archive and get the checksum
    ostream = Gio.MemoryOutputStream.new_resizable()
    ufile.get_repacked_cabinet().write_simple(ostream)
    cab_data = Gio.MemoryOutputStream.steal_as_bytes(ostream).get_data()
    checksum_container = hashlib.sha1(cab_data).hexdigest()

    # dump to a file
    download_dir = app.config['DOWNLOAD_DIR']
    if not os.path.exists(download_dir):
        os.mkdir(download_dir)
    fn = os.path.join(download_dir, ufile.filename_new)
    open(fn, 'wb').write(cab_data)

    # inform the plugin loader
    ploader.file_modified(fn)

    # create parent firmware object
    target = request.form['target']
    fw = Firmware()
    fw.group_id = g.user.group_id
    fw.addr = _get_client_address()
    fw.filename = ufile.filename_new
    fw.firmware_id = ufile.firmware_id
    fw.target = target
    if ufile._version_inf_display:
        fw.version_display = ufile._version_inf_display[1]

    # create child metadata object for the component
    for component in ufile.get_components():
        md = FirmwareMd()
        md.firmware_id = ufile.firmware_id
        md.metainfo_id = component.get_metadata_item('metainfo_id')
        md.cid = component.get_id()
        md.name = component.get_name()
        md.summary = component.get_comment()
        md.developer_name = component.get_developer_name()
        md.metadata_license = component.get_metadata_license()
        md.project_license = component.get_project_license()
        md.url_homepage = component.get_url_item(AppStreamGlib.UrlKind.HOMEPAGE)
        md.description = component.get_description()
        md.checksum_container = checksum_container

        # from the provide
        for prov in component.get_provides():
            if prov.get_kind() != AppStreamGlib.ProvideKind.FIRMWARE_FLASHED:
                continue
            md.guids.append(prov.get_value())

        # from the release
        rel = component.get_release_default()
        md.version = rel.get_version()
        md.release_description = rel.get_description()
        md.release_timestamp = rel.get_timestamp()
        md.release_installed_size = rel.get_size(AppStreamGlib.SizeKind.INSTALLED)
        md.release_download_size = rel.get_size(AppStreamGlib.SizeKind.DOWNLOAD)
        md.release_urgency = AppStreamGlib.urgency_kind_to_string(rel.get_urgency())

        # from requires
        for req in component.get_requires():
            fwreq = FirmwareRequirement(AppStreamGlib.Require.kind_to_string(req.get_kind()),
                                        req.get_value(),
                                        AppStreamGlib.Require.compare_to_string(req.get_compare()),
                                        req.get_version())
            md.requirements.append(fwreq)

        # from the first screenshot
        if len(component.get_screenshots()) > 0:
            ss = component.get_screenshots()[0]
            md.screenshot_caption = ss.get_caption(None)
            if len(ss.get_images()) > 0:
                im = ss.get_images()[0]
                md.screenshot_url = im.get_url()

        # from the content checksum
        csum = rel.get_checksum_by_target(AppStreamGlib.ChecksumTarget.CONTENT)
        md.checksum_contents = csum.get_value()
        md.filename_contents = csum.get_filename()

        fw.mds.append(md)

    # add to database
    db.firmware.add(fw)

    # set correct response code
    _event_log("Uploaded file %s to %s" % (ufile.filename_new, target))

    # ensure up to date
    if target == 'embargo':
        _metadata_update_group(fw.group_id)
    if target == 'stable':
        _metadata_update_targets(['stable', 'testing'])
    elif target == 'testing':
        _metadata_update_targets(['testing'])

    return redirect(url_for('.firmware_show', firmware_id=ufile.firmware_id))

@app.route('/lvfs/analytics')
@app.route('/lvfs/analytics/month')
@login_required
def analytics_month():
    """ A analytics screen to show information about users """

    # security check
    if not g.user.check_capability(UserCapability.Admin):
        return _error_permission_denied('Unable to view analytics')
    labels_days = _get_chart_labels_days()[::-1]
    data_days = db.clients.get_stats_for_month(DownloadKind.FIRMWARE)[::-1]
    return render_template('analytics-month.html',
                           labels_days=labels_days,
                           data_days=data_days)

@app.route('/lvfs/analytics/year')
@login_required
def analytics_year():
    """ A analytics screen to show information about users """

    # security check
    if not g.user.check_capability(UserCapability.Admin):
        return _error_permission_denied('Unable to view analytics')
    labels_months = _get_chart_labels_months()[::-1]
    data_months = db.clients.get_stats_for_year(DownloadKind.FIRMWARE)[::-1]
    return render_template('analytics-year.html',
                           labels_months=labels_months,
                           data_months=data_months)

@app.route('/lvfs/analytics/user_agent')
@login_required
def analytics_user_agents():
    """ A analytics screen to show information about users """

    # security check
    if not g.user.check_capability(UserCapability.Admin):
        return _error_permission_denied('Unable to view analytics')
    labels_user_agent, data_user_agent = db.clients.get_user_agent_stats()
    return render_template('analytics-user-agent.html',
                           labels_user_agent=labels_user_agent,
                           data_user_agent=data_user_agent)

@app.route('/lvfs/analytics/clients')
@login_required
def analytics_clients():
    """ A analytics screen to show information about users """

    # security check
    if not g.user.check_capability(UserCapability.Admin):
        return _error_permission_denied('Unable to view analytics')
    clients = db.clients.get_all(limit=25)
    return render_template('analytics-clients.html', clients=clients)

@app.route('/lvfs/analytics/reports')
@login_required
def analytics_reports():
    """ A analytics screen to show information about users """

    # security check
    if not g.user.check_capability(UserCapability.Admin):
        return _error_permission_denied('Unable to view analytics')
    reports = db.reports.get_all(limit=25)
    return render_template('analytics-reports.html', reports=reports)

@app.route('/lvfs/report/<report_id>')
@login_required
def report_view(report_id):
    if not g.user.check_capability(UserCapability.Admin):
        return _error_permission_denied('Unable to view report')
    rprt = db.reports.find_by_id(report_id)
    if not rprt:
        return _error_permission_denied('Report does not exist')
    return Response(response=rprt.json,
                    status=400, \
                    mimetype="application/json")

@app.route('/lvfs/report/<report_id>/delete')
@login_required
def report_delete(report_id):
    if not g.user.check_capability(UserCapability.Admin):
        return _error_permission_denied('Unable to view report')
    db.reports.remove_by_id(report_id)
    return redirect(url_for('.analytics_reports'))

@app.route('/lvfs/login', methods=['POST'])
def login():
    """ A login screen to allow access to the LVFS main page """
    # auth check
    user = None
    password = _password_hash(request.form['password'])
    user = db.users.get_item(request.form['username'], password)
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
        eventlog_len = db.eventlog.size()
    else:
        eventlog_len = db.eventlog.size_for_group_id(g.user.group_id)
    nr_pages = int(math.ceil(eventlog_len / float(length)))

    # table contents
    if g.user.check_capability(UserCapability.Admin):
        events = db.eventlog.get_all(int(start), int(length))
    else:
        events = db.eventlog.get_all_for_group_id(g.user.group_id, int(start), int(length))
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

@app.route('/lvfs/settings')
@app.route('/lvfs/settings/<plugin_id>')
@login_required
def settings_view(plugin_id='general'):
    """
    Allows the admin to change details about the LVFS instance
    """

    # security check
    if not g.user.check_capability(UserCapability.Admin):
        return _error_permission_denied('Only admin is allowed to change settings')

    # get all settings
    settings = db.settings.get_all()
    plugins = ploader.get_all()
    for p in plugins:
        for s in p.settings():
            if s.key not in settings:
                db.settings.add(s.key, s.default)
    return render_template('settings.html',
                           settings=settings,
                           plugin_id=plugin_id,
                           plugins=plugins)

@app.route('/lvfs/settings/modify', methods=['GET', 'POST'])
@app.route('/lvfs/settings/modify/<plugin_id>', methods=['GET', 'POST'])
@login_required
def settings_modify(plugin_id='general'):
    """ Change details about the instance """

    # only accept form data
    if request.method != 'POST':
        return redirect(url_for('.settings_view', plugin_id=plugin_id))

    # security check
    if not g.user.check_capability(UserCapability.Admin):
        return _error_permission_denied('Unable to modify settings as non-admin')

    # save new values
    settings = db.settings.get_all()
    for key in request.form:
        if settings[key] == request.form[key]:
            continue
        _event_log('Changed server settings %s to %s' % (key, request.form[key]))
        db.settings.modify(key, request.form[key])
    flash('Updated settings', 'info')
    return redirect(url_for('.settings_view', plugin_id=plugin_id), 302)

@app.route('/lvfs/metadata_rebuild')
@login_required
def metadata_rebuild():
    """
    Forces a rebuild of all metadata.
    """

    # security check
    if not g.user.check_capability(UserCapability.Admin):
        return _error_permission_denied('Only admin is allowed to force-rebuild metadata')

    # update metadata
    for group in db.groups.get_all():
        _metadata_update_group(group.group_id)
    _metadata_update_targets(['stable', 'testing'])
    _metadata_update_pulp()
    return redirect(url_for('.metadata_view'))
