#!/usr/bin/python2
# -*- coding: utf-8 -*-
#
# Copyright (C) 2015-2017 Richard Hughes <richard@hughsie.com>
# Licensed under the GNU General Public License Version 2

import os
import datetime
import hashlib
import math
import ConfigParser

import cabarchive
import appstream

from flask import session, request, flash, url_for, redirect, render_template
from flask import send_from_directory, abort, make_response
from flask.ext.login import login_required, login_user, logout_user

from app import app, db, lm

from .db import CursorError
from .models import Firmware, FirmwareMd, FirmwareRequirement, DownloadKind
from .affidavit import NoKeyError
from .inf_parser import InfParser
from .hash import _qa_hash, _password_hash
from .util import _create_affidavit, _event_log, _get_client_address
from .util import _error_internal, _error_permission_denied
from .util import _get_chart_labels_months, _get_chart_labels_days
from .metadata import _metadata_update_group, _metadata_update_targets, _metadata_update_pulp

def _check_session():
    if 'username' not in session:
        return False
    if 'group_id' not in session:
        return False
    if 'qa_capability' not in session:
        return False
    if 'is_locked' not in session:
        return False
    return True

################################################################################

@app.route('/<path:resource>')
def serveStaticResource(resource):
    """ Return a static image or resource """

    # ban MJ12BOT, it ignores robots.txt
    user_agent = request.headers.get('User-Agent')
    if user_agent and user_agent.find('MJ12BOT') != -1:
        abort(403)

    # log certain kinds of files
    if resource.endswith('.cab'):
        try:
            db.clients.add(datetime.date.today(), DownloadKind.FIRMWARE)
            db.clients.increment(_get_client_address(),
                                 os.path.basename(resource),
                                 user_agent)
        except CursorError as e:
            print str(e)

    # firmware blobs can be stored on a CDN
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
        if type(num) not in (int, long):
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
    print "generic error handler"
    return _error_permission_denied(msg)

@app.route('/developers')
def developers():
    return render_template('developers.html')

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
    default_admin_password = False
    if user and user.password == '5459dbe5e9aa80e077bfa40f3fb2ca8368ed09b4':
        default_admin_password = True
    return render_template('index.html',
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
    try:
        item = db.groups.get_item(qa_group)
    except CursorError as e:
        return _error_internal(str(e))
    if not item:
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
def metadata():
    """
    Show all metadata available to this user.
    """

    # show all embargo metadata URLs when admin user
    group_ids = []
    if session['group_id'] == 'admin':
        try:
            groups = db.groups.get_all()
            for group in groups:
                group_ids.append(group.group_id)
        except CursorError as e:
            return _error_internal(str(e))
    else:
        group_ids.append(session['group_id'])
    return render_template('metadata.html',
                           group_id=session['group_id'],
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
        try:
            item = db.groups.get_item(session['group_id'])
        except CursorError as e:
            return _error_internal(str(e))
        if item:
            vendor_ids.extend(item.vendor_ids)
        return render_template('upload.html', vendor_ids=vendor_ids)

    # not correct parameters
    if not 'target' in request.form:
        return _error_internal('No target')
    if not 'file' in request.files:
        return _error_internal('No file')

    # can the user upload directly to stable
    if request.form['target'] in ['stable', 'testing']:
        if not session['qa_capability']:
            return _error_permission_denied('Unable to upload to this target as not QA user')

    # check size < 50Mb
    fileitem = request.files['file']
    if not fileitem:
        return _error_internal('No file object')
    data = fileitem.read()
    if len(data) > 50000000:
        return _error_internal('File too large, limit is 50Mb', 413)
    if len(data) == 0:
        return _error_internal('File has no content')
    if len(data) < 1024:
        return _error_internal('File too small, mimimum is 1k')

    # check the file does not already exist
    firmware_id = hashlib.sha1(data).hexdigest()
    try:
        item = db.firmware.get_item(firmware_id)
    except CursorError as e:
        return _error_internal(str(e))
    if item:
        return _error_internal("A firmware file with hash %s already exists" % firmware_id, 422)

    # parse the file
    arc = cabarchive.CabArchive()
    try:
        cabextract_cmd = app.config['CABEXTRACT_CMD']
        if os.path.exists(cabextract_cmd):
            arc.set_decompressor(cabextract_cmd)
        arc.parse(data)
    except cabarchive.CorruptionError as e:
        return _error_internal('Invalid file type: %s' % str(e), 415)
    except cabarchive.NotSupportedError as e:
        return _error_internal('The file is unsupported: %s' % str(e), 415)

    # check .inf exists
    fw_version_inf = None
    fw_version_display_inf = None
    cf = arc.find_file("*.inf")
    if cf:
        if cf.contents.find('FIXME') != -1:
            return _error_internal("The inf file was not complete; "
                                   "Any FIXME text must be replaced with the correct values.")

        # check .inf file is valid
        cfg = InfParser()
        cfg.read_data(cf.contents)
        try:
            tmp = cfg.get('Version', 'Class')
        except (ConfigParser.NoOptionError, ConfigParser.NoSectionError) as e:
            return _error_internal('The inf file Version:Class was missing')
        if tmp != 'Firmware':
            return _error_internal('The inf file Version:Class was invalid')
        try:
            tmp = cfg.get('Version', 'ClassGuid')
        except ConfigParser.NoOptionError as e:
            return _error_internal('The inf file Version:ClassGuid was missing')
        if tmp != '{f2e7dd72-6468-4e36-b6f1-6488f42c1b52}':
            return _error_internal('The inf file Version:ClassGuid was invalid')
        try:
            tmp = cfg.get('Version', 'DriverVer')
            fw_version_display_inf = tmp.split(',')
            if len(fw_version_display_inf) != 2:
                return _error_internal('The inf file Version:DriverVer was invalid')
        except ConfigParser.NoOptionError as e:
            pass

        # this is optional, but if supplied must match the version in the XML
        # -- also note this will not work with multi-firmware .cab files
        try:
            fw_version_inf = cfg.get('Firmware_AddReg', 'HKR->FirmwareVersion')
            if fw_version_inf.startswith('0x'):
                fw_version_inf = str(int(fw_version_inf[2:], 16))
            if fw_version_inf == '0':
                fw_version_inf = None
        except (ConfigParser.NoOptionError, ConfigParser.NoSectionError) as e:
            pass

    # check metainfo exists
    cfs = arc.find_files("*.metainfo.xml")
    if len(cfs) == 0:
        return _error_internal('The firmware file had no .metadata.xml files')

    # parse each MetaInfo file
    apps = []
    for cf in cfs:
        component = appstream.Component()
        try:
            component.parse(str(cf.contents))
            component.validate()
        except appstream.ParseError as e:
            return _error_internal('The metadata %s could not be parsed: %s' % (cf, str(e)))
        except appstream.ValidationError as e:
            return _error_internal('The metadata %s file did not validate: %s' % (cf, str(e)))

        # get the metadata ID
        component.custom['metainfo_id'] = hashlib.sha1(cf.contents).hexdigest()

        # check the file does not have any missing request.form
        if cf.contents.find('FIXME') != -1:
            return _error_internal("The metadata file was not complete; "
                                   "Any FIXME text must be replaced with the correct values.")

        # check the firmware provides something
        if len(component.provides) == 0:
            return _error_internal("The metadata file did not provide any GUID.")
        if len(component.releases) == 0:
            return _error_internal("The metadata file did not provide any releases.")

        # check the inf file matches up with the .xml file
        if fw_version_inf and fw_version_inf != component.releases[0].version:
            return _error_internal("The inf Firmware_AddReg[HKR->FirmwareVersion] "
                                   "'%s' did not match the metainfo.xml value '%s'."
                                   % (fw_version_inf, component.releases[0].version))

        # check the guid and version does not already exist
        try:
            items = db.firmware.get_all()
        except CursorError as e:
            return _error_internal(str(e))
        for item in items:
            for md in item.mds:
                for guid in md.guids:
                    if guid == component.provides[0].value and md.version == component.releases[0].version:
                        return _error_internal("A firmware file for this version already exists", 422)

        # check if the file dropped a GUID previously supported
        new_guids = []
        for prov in component.provides:
            new_guids.append(prov.value)
        for item in items:
            for md in item.mds:
                if md.cid != component.id:
                    continue
                for old_guid in md.guids:
                    if not old_guid in new_guids:
                        return _error_internal("Firmware %s dropped a GUID previously supported %s" % (md.cid, old_guid), 422)

        # check the file didn't try to add it's own <require> on vendor-id
        # to work around the vendor-id security checks in fwupd
        req = component.get_require_by_kind('firmware', 'vendor-id')
        if req:
            return _error_internal("Firmware cannot specify vendor-id", 422)

        # add to array
        apps.append(component)

    # only save if we passed all tests
    basename = os.path.basename(fileitem.filename)
    new_filename = firmware_id + '-' + basename

    # add these after parsing in case multiple components use the same file
    asc_files = {}

    # fix up the checksums and add the detached signature
    for component in apps:

        # ensure there's always a container checksum
        release = component.releases[0]
        csum = release.get_checksum_by_target('content')
        if not csum:
            csum = appstream.Checksum()
            csum.target = 'content'
            csum.filename = 'firmware.bin'
            component.releases[0].add_checksum(csum)

        # get the contents checksum
        fw_data = arc.find_file(csum.filename)
        if not fw_data:
            return _error_internal('No %s found in the archive' % csum.filename)
        csum.kind = 'sha1'
        csum.value = hashlib.sha1(fw_data.contents).hexdigest()

        # set the sizes
        release.size_installed = len(fw_data.contents)
        release.size_download = len(data)

        # add the detached signature if not already signed
        sig_data = arc.find_file(csum.filename + ".asc")
        if not sig_data:
            if csum.filename not in asc_files:
                try:
                    affidavit = _create_affidavit()
                except NoKeyError as e:
                    return _error_internal('Failed to sign archive: ' + str(e))
                cff = cabarchive.CabFile(fw_data.filename + '.asc',
                                         affidavit.create(fw_data.contents))
                asc_files[csum.filename] = cff
        else:
            # check this file is signed by something we trust
            try:
                affidavit = _create_affidavit()
                affidavit.verify(fw_data.contents)
            except NoKeyError as e:
                return _error_internal('Failed to verify archive: ' + str(e))

    # add all the .asc files to the archive
    for key in asc_files:
        arc.add_file(asc_files[key])

    # export the new archive and get the checksum
    cab_data = arc.save(compressed=True)
    checksum_container = hashlib.sha1(cab_data).hexdigest()

    # dump to a file
    download_dir = app.config['DOWNLOAD_DIR']
    if not os.path.exists(download_dir):
        os.mkdir(download_dir)
    fn = os.path.join(download_dir, new_filename)
    open(fn, 'wb').write(cab_data)

    # create parent firmware object
    target = request.form['target']
    fwobj = Firmware()
    fwobj.group_id = session['group_id']
    fwobj.addr = _get_client_address()
    fwobj.filename = new_filename
    fwobj.firmware_id = firmware_id
    fwobj.target = target
    if fw_version_display_inf:
        fwobj.version_display = fw_version_display_inf[1]

    # create child metadata object for the component
    for component in apps:
        md = FirmwareMd()
        md.firmware_id = firmware_id
        md.metainfo_id = component.custom['metainfo_id']
        md.cid = component.id
        md.name = component.name
        md.summary = component.summary
        md.developer_name = component.developer_name
        md.metadata_license = component.metadata_license
        md.project_license = component.project_license
        md.url_homepage = component.urls['homepage']
        md.description = component.description
        md.checksum_container = checksum_container

        # from the provide
        for prov in component.provides:
            md.guids.append(prov.value)

        # from the release
        rel = component.releases[0]
        md.version = rel.version
        md.release_description = rel.description
        md.release_timestamp = rel.timestamp
        md.release_installed_size = rel.size_installed
        md.release_download_size = rel.size_download
        md.release_urgency = rel.urgency

        # from requires
        for req in component.requires:
            fwreq = FirmwareRequirement(req.kind, req.value, req.compare, req.version)
            md.requirements.append(fwreq)

        # from the first screenshot
        if len(component.screenshots) > 0:
            ss = component.screenshots[0]
            if ss.caption:
                md.screenshot_caption = ss.caption
            if len(ss.images) > 0:
                im = ss.images[0]
                if im.url:
                    md.screenshot_url = im.url

        # from the content checksum
        csum = component.releases[0].get_checksum_by_target('content')
        md.checksum_contents = csum.value
        md.filename_contents = csum.filename

        fwobj.mds.append(md)

    # add to database
    try:
        db.firmware.add(fwobj)
    except CursorError as e:
        return _error_internal(str(e))
    # set correct response code
    _event_log("Uploaded file %s to %s" % (new_filename, target))

    # ensure up to date
    try:
        if target == 'embargo':
            _metadata_update_group(fwobj.group_id)
        if target == 'stable':
            _metadata_update_targets(['stable', 'testing'])
        elif target == 'testing':
            _metadata_update_targets(['testing'])

    except NoKeyError as e:
        return _error_internal('Failed to sign metadata: ' + str(e))
    except CursorError as e:
        return _error_internal('Failed to generate metadata: ' + str(e))

    return redirect(url_for('.firmware_show', firmware_id=firmware_id))

@app.route('/lvfs/analytics')
@app.route('/lvfs/analytics/month')
@login_required
def analytics_month():
    """ A analytics screen to show information about users """

    # security check
    if session['group_id'] != 'admin':
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
    if session['group_id'] != 'admin':
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
    if session['group_id'] != 'admin':
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
    if session['group_id'] != 'admin':
        return _error_permission_denied('Unable to view analytics')
    clients = db.clients.get_all(limit=25)
    return render_template('analytics-clients.html', clients=clients)

@app.route('/lvfs/login', methods=['POST'])
def login():
    """ A login screen to allow access to the LVFS main page """
    # auth check
    user = None
    password = _password_hash(request.form['password'])
    try:
        user = db.users.get_item(request.form['username'],
                                 password)
    except CursorError as e:
        return _error_internal(str(e))
    if not user:
        # log failure
        _event_log('Failed login attempt for %s' % request.form['username'])
        flash('Incorrect username or password', 'error')
        return redirect(url_for('.index'))
    if not user.is_enabled:
        # log failure
        _event_log('Failed login attempt for %s (user disabled)' % request.form['username'])
        flash('User account is disabled', 'error')
        return redirect(url_for('.index'))

    # this is signed, not encrypted
    session['username'] = user.username
    session['qa_capability'] = user.is_qa
    session['group_id'] = user.group_id
    session['is_locked'] = user.is_locked
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
    if not session['qa_capability']:
        return _error_permission_denied('Unable to show event log for non-QA user')

    # get the page selection correct
    if session['group_id'] == 'admin':
        eventlog_len = db.eventlog.size()
    else:
        eventlog_len = db.eventlog.size_for_group_id(session['group_id'])
    nr_pages = int(math.ceil(eventlog_len / float(length)))

    # table contents
    try:
        if session['group_id'] == 'admin':
            items = db.eventlog.get_all(int(start), int(length))
        else:
            items = db.eventlog.get_all_for_group_id(session['group_id'], int(start), int(length))
    except CursorError as e:
        return _error_internal(str(e))
    if len(items) == 0:
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
    return render_template('eventlog.html', events=items, pagination_footer=html)

def _update_metadata_from_fn(fwobj, fn):
    """
    Re-parses the .cab file and updates the database version.
    """

    # load cab file
    arc = cabarchive.CabArchive()
    try:
        cabextract_cmd = app.config['CABEXTRACT_CMD']
        if os.path.exists(cabextract_cmd):
            arc.set_decompressor(cabextract_cmd)
        arc.parse_file(fn)
    except cabarchive.CorruptionError as e:
        return _error_internal('Invalid file type: %s' % str(e))

    # parse the MetaInfo file
    cf = arc.find_file("*.metainfo.xml")
    if not cf:
        return _error_internal('The firmware file had no valid metadata')
    component = appstream.Component()
    try:
        component.parse(str(cf.contents))
    except appstream.ParseError as e:
        return _error_internal('The metadata could not be parsed: ' + str(e))

    # parse the inf file
    cf = arc.find_file("*.inf")
    if not cf:
        return _error_internal('The firmware file had no valid inf file')
    cfg = InfParser()
    cfg.read_data(cf.contents)
    try:
        tmp = cfg.get('Version', 'DriverVer')
        driver_ver = tmp.split(',')
        if len(driver_ver) != 2:
            return _error_internal('The inf file Version:DriverVer was invalid')
    except ConfigParser.NoOptionError as e:
        driver_ver = None

    # get the contents
    fw_data = arc.find_file('*.bin')
    if not fw_data:
        fw_data = arc.find_file('*.rom')
    if not fw_data:
        fw_data = arc.find_file('*.cap')
    if not fw_data:
        return _error_internal('No firmware found in the archive')

    # update sizes
    fwobj.mds[0].release_installed_size = len(fw_data.contents)
    fwobj.mds[0].release_download_size = os.path.getsize(fn)

    # update the descriptions
    fwobj.mds[0].release_description = component.releases[0].description
    fwobj.mds[0].description = component.description
    if driver_ver:
        fwobj.version_display = driver_ver[1]
    db.firmware.update(fwobj)
    return None

@app.route('/lvfs/profile')
@login_required
def profile():
    """
    Allows the normal user to change details about the account,
    """

    # security check
    if session['is_locked']:
        return _error_permission_denied('Unable to view profile as account locked')

    # auth check
    try:
        item = db.users.get_item(session['username'])
    except CursorError as e:
        return _error_internal(str(e))
    if not item:
        return _error_internal('Invalid username query')

    # add defaults
    if not item.display_name:
        item.display_name = "Example Name"
    if not item.email:
        item.email = "info@example.com"
    return render_template('profile.html',
                           vendor_name=item.display_name,
                           contact_email=item.email,
                           pubkey=item.pubkey)

@app.route('/lvfs/metadata_rebuild')
@login_required
def metadata_rebuild():
    """
    Forces a rebuild of all metadata.
    """

    # security check
    if session['group_id'] != 'admin':
        return _error_permission_denied('Only admin is allowed to force-rebuild metadata')

    # update metadata
    try:
        for group in db.groups.get_all():
            _metadata_update_group(group.group_id)
        _metadata_update_targets(['stable', 'testing'])
        _metadata_update_pulp()
    except NoKeyError as e:
        return _error_internal('Failed to sign metadata: ' + str(e))
    except CursorError as e:
        return _error_internal('Failed to generate metadata: ' + str(e))
    return redirect(url_for('.metadata'))
