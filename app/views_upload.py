#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2015-2018 Richard Hughes <richard@hughsie.com>
# Licensed under the GNU General Public License Version 2
#
# pylint: disable=too-many-locals

import os
import datetime
import hashlib

from gi.repository import AppStreamGlib
from gi.repository import Gio
from gi.repository import GLib

from flask import request, flash, url_for, redirect, render_template, g
from flask_login import login_required

from app import app, db, ploader

from .models import Firmware, Component, Requirement, Guid, FirmwareEvent
from .models import Vendor, Remote, Agreement, Affiliation, Checksum, Protocol
from .uploadedfile import UploadedFile, FileTooLarge, FileTooSmall, FileNotSupported, MetadataInvalid
from .util import _get_client_address, _get_settings, _markdown_from_xml
from .util import _error_internal, _error_permission_denied
from .util import _json_success, _json_error
from .views_firmware import _firmware_delete

def _get_plugin_metadata_for_uploaded_file(ufile):
    settings = _get_settings()
    metadata = {}
    metadata['$DATE$'] = datetime.datetime.now().replace(microsecond=0).isoformat()
    metadata['$FWUPD_MIN_VERSION$'] = ufile.fwupd_min_version
    metadata['$CAB_FILENAME$'] = ufile.filename_new
    metadata['$FIRMWARE_BASEURI$'] = settings['firmware_baseuri']
    return metadata

def _user_can_upload(user):

    # never signed anything
    if not user.agreement:
        return False

    # is it up to date?
    agreement = db.session.query(Agreement).\
                    order_by(Agreement.version.desc()).first()
    if not agreement:
        return False
    if user.agreement.version < agreement.version:
        return False

    # works for us
    return True

def _create_fw_from_uploaded_file(ufile):

    # create empty firmware
    fw = Firmware()
    fw.filename = ufile.filename_new
    fw.checksum_upload = ufile.checksum_upload
    if ufile.version_display:
        fw.version_display = ufile.version_display

    # create child metadata object for the components
    for component in ufile.get_components():
        md = Component()
        md.appstream_id = component.get_id()
        md.name = str(component.get_name())
        md.summary = str(component.get_comment())
        md.developer_name = str(component.get_developer_name())
        md.metadata_license = component.get_metadata_license()
        md.project_license = component.get_project_license()
        md.url_homepage = str(component.get_url_item(AppStreamGlib.UrlKind.HOMEPAGE))
        md.description = _markdown_from_xml(str(component.get_description()))
        md.priority = component.get_priority()

        # fix up the vendor
        if md.developer_name == 'LenovoLtd.':
            md.developer_name = 'Lenovo Ltd.'

        # add manually added keywords
        for keyword in component.get_keywords():
            md.add_keywords_from_string(str(keyword), priority=5)

        # add from the provided free text
        if md.developer_name:
            md.add_keywords_from_string(md.developer_name, priority=10)
        if md.name:
            md.add_keywords_from_string(md.name, priority=3)
        if md.summary:
            md.add_keywords_from_string(md.summary, priority=1)

        # from the provide
        for prov in component.get_provides():
            if prov.get_kind() != AppStreamGlib.ProvideKind.FIRMWARE_FLASHED:
                continue
            md.guids.append(Guid(md.component_id, prov.get_value()))

        # from the release
        rel = component.get_release_default()
        md.version = rel.get_version()
        #allows this to work on older versions of appstream-glib
        if hasattr(rel, 'get_object_duration'):
            md.install_duration = rel.get_install_duration()
        else:
            md.install_duration = 0
        md.release_description = _markdown_from_xml(str(rel.get_description()))
        md.release_timestamp = rel.get_timestamp()
        md.release_installed_size = rel.get_size(AppStreamGlib.SizeKind.INSTALLED)
        md.release_download_size = rel.get_size(AppStreamGlib.SizeKind.DOWNLOAD)
        md.release_urgency = AppStreamGlib.urgency_kind_to_string(rel.get_urgency())
        if hasattr(AppStreamGlib.UrlKind, 'DETAILS'):
            md.details_url = str(rel.get_url(AppStreamGlib.UrlKind.DETAILS)) # pylint: disable=no-member
        if hasattr(AppStreamGlib.UrlKind, 'SOURCE'):
            md.source_url = str(rel.get_url(AppStreamGlib.UrlKind.SOURCE)) # pylint: disable=no-member

        # from requires
        for req in component.get_requires():
            req_kind = AppStreamGlib.Require.kind_to_string(req.get_kind())
            req_compare = AppStreamGlib.Require.compare_to_string(req.get_compare())
            req_value = req.get_value()
            if req_kind == 'hardware':
                req_values = req_value.split('|')
            else:
                req_values = [req_value]
            for req_value in req_values:
                rq = Requirement(md.component_id,
                                 req_kind, req_value, req_compare,
                                 req.get_version())
                md.requirements.append(rq)

        # from the first screenshot
        if len(component.get_screenshots()) > 0:
            ss = component.get_screenshots()[0]
            tmp = ss.get_caption(None)
            tmp = tmp.replace('<p>', '')
            tmp = tmp.replace('</p>', '')
            md.screenshot_caption = tmp
            if len(ss.get_images()) > 0:
                im = ss.get_images()[0]
                md.screenshot_url = str(im.get_url())

        # from the content checksum
        csum = rel.get_checksum_by_target(AppStreamGlib.ChecksumTarget.CONTENT)
        md.checksum_contents = csum.get_value()
        md.filename_contents = csum.get_filename()

        # from the device checksum
        if hasattr(AppStreamGlib.ChecksumTarget, 'DEVICE'):
            for csum in rel.get_checksums():
                if csum.get_target() == AppStreamGlib.ChecksumTarget.DEVICE: # pylint: disable=no-member
                    if csum.get_kind() == GLib.ChecksumType.SHA1:
                        md.device_checksums.append(Checksum(csum.get_value(), 'SHA1'))
                    elif csum.get_kind() == GLib.ChecksumType.SHA256:
                        md.device_checksums.append(Checksum(csum.get_value(), 'SHA256'))

        fw.mds.append(md)

    return fw

def _filter_fw_by_id_guid_version(fws, component_id, provides_value, release_version):
    for fw in fws:
        if fw.is_deleted:
            continue
        for md in fw.mds:
            if md.component_id != component_id:
                continue
            for guid in md.guids:
                if guid.value == provides_value and md.version == release_version:
                    return fw
    return None

@app.route('/lvfs/upload', methods=['GET', 'POST'])
@login_required
def upload():
    """ Upload a .cab file to the LVFS service """

    # only accept form data
    if request.method != 'POST':
        if not hasattr(g, 'user'):
            return redirect(url_for('.index'))
        if not _user_can_upload(g.user):
            return redirect(url_for('.agreement_show'))
        vendor_ids = []
        vendor = db.session.query(Vendor).filter(Vendor.vendor_id == g.user.vendor_id).first()
        if vendor:
            for res in vendor.restrictions:
                vendor_ids.append(res.value)
        affiliations = db.session.query(Affiliation).\
                        filter(Affiliation.vendor_id_odm == g.user.vendor_id).all()
        return render_template('upload.html', vendor_ids=vendor_ids, affiliations=affiliations)

    # verify the user can upload
    if not _user_can_upload(g.user):
        return _error_permission_denied('User has not signed legal agreement')

    # used a custom vendor_id
    if 'vendor_id' in request.form:
        try:
            vendor_id = int(request.form['vendor_id'])
        except ValueError as e:
            flash('Failed to upload file: Specified vendor ID %s invalid' % request.form['vendor_id'], 'warning')
            return redirect('/lvfs/upload')
        vendor = db.session.query(Vendor).filter(Vendor.vendor_id == vendor_id).first()
        if not vendor:
            flash('Failed to upload file: Specified vendor ID not found', 'warning')
            return redirect('/lvfs/upload')
    else:
        vendor = g.user.vendor

    # security check
    if not vendor.check_acl('@upload'):
        flash('Failed to upload file for vendor: Permission denied: '
              'User with vendor %s cannot upload to vendor %s' %
              (g.user.vendor.group_id, vendor.group_id), 'warning')
        return redirect('/lvfs/upload')

    # not correct parameters
    if not 'target' in request.form:
        return _error_internal('No target')
    if not 'file' in request.files:
        return _error_internal('No file')
    if request.form['target'] not in ['private', 'embargo', 'testing']:
        return _error_internal('Target not valid')

    # find remote, creating if required
    remote_name = request.form['target']
    if remote_name == 'embargo':
        remote = vendor.remote
    else:
        remote = db.session.query(Remote).filter(Remote.name == remote_name).first()
    if not remote:
        return _error_internal('No remote for target %s' % remote_name)

    # load in the archive
    fileitem = request.files['file']
    if not fileitem:
        return _error_internal('No file object')
    try:
        ufile = UploadedFile()
        ufile.parse(os.path.basename(fileitem.filename), fileitem.read())
    except (FileTooLarge, FileTooSmall, FileNotSupported, MetadataInvalid) as e:
        flash('Failed to upload file: ' + str(e), 'danger')
        return redirect(request.url)

    # check the file does not already exist
    fw = db.session.query(Firmware).filter(Firmware.checksum_upload == ufile.checksum_upload).first()
    if fw:
        if fw.check_acl('@view'):
            flash('Failed to upload file: A file with hash %s already exists' % fw.checksum_upload, 'warning')
            return redirect('/lvfs/firmware/%s' % fw.firmware_id)
        flash('Failed to upload file: Another user has already uploaded this firmware', 'warning')
        return redirect('/lvfs/upload')

    # check the guid and version does not already exist
    fws = db.session.query(Firmware).all()
    fws_already_exist = []
    for component in ufile.get_components():
        provides_value = component.get_provides()[0].get_value()
        release_default = component.get_release_default()
        release_version = release_default.get_version()
        component_id = component.get_id()
        fw = _filter_fw_by_id_guid_version(fws,
                                           component_id,
                                           provides_value,
                                           release_version)
        if fw:
            fws_already_exist.append(fw)

    # all the components existed, so build an error out of all the versions
    if len(fws_already_exist) == len(ufile.get_components()):
        if g.user.is_robot and 'auto-delete' in request.form:
            for fw in fws_already_exist:
                if fw.remote.is_public:
                    return _error_permission_denied('Firmware %i cannot be autodeleted as is in remote %s' %
                                                    (fw.firmware_id, fw.remote.name))
                if fw.user.user_id != g.user.user_id:
                    return _error_permission_denied('Firmware was not uploaded by this user')
            for fw in fws_already_exist:
                flash('Firmware %i was auto-deleted due to robot upload' % fw.firmware_id)
                _firmware_delete(fw)
        else:
            versions_for_display = []
            for fw in fws_already_exist:
                for md in fw.mds:
                    if not md.version_display in versions_for_display:
                        versions_for_display.append(md.version_display)
            flash('Failed to upload file: A firmware file for this device with '
                  'version %s already exists' % ','.join(versions_for_display), 'danger')
            return redirect('/lvfs/firmware/%s' % fw.firmware_id)

    # check if the file dropped a GUID previously supported
    for component in ufile.get_components():
        new_guids = []
        for prov in component.get_provides():
            if prov.get_kind() != AppStreamGlib.ProvideKind.FIRMWARE_FLASHED:
                continue
            new_guids.append(prov.get_value())
        for fw in fws:
            if fw.is_deleted:
                continue
            for md in fw.mds:
                if md.appstream_id != component.get_id():
                    continue
                for old_guid in md.guids:
                    if not old_guid.value in new_guids:
                        flash('Firmware %s dropped a GUID previously '
                              'supported %s' % (md.appstream_id, old_guid.value), 'danger')
                        return redirect(request.url)

    # allow plugins to copy any extra files from the source archive
    for cffolder in ufile.get_source_cabinet().get_folders():
        for cffile in cffolder.get_files():
            ploader.archive_copy(ufile.get_repacked_cabinet(), cffile)

    # allow plugins to add files
    ploader.archive_finalize(ufile.get_repacked_cabinet(),
                             _get_plugin_metadata_for_uploaded_file(ufile))

    # export the new archive and get the checksum
    ostream = Gio.MemoryOutputStream.new_resizable()
    ufile.get_repacked_cabinet().write_simple(ostream)
    cab_data = Gio.MemoryOutputStream.steal_as_bytes(ostream).get_data()

    # dump to a file
    download_dir = app.config['DOWNLOAD_DIR']
    if not os.path.exists(download_dir):
        os.mkdir(download_dir)
    fn = os.path.join(download_dir, ufile.filename_new)
    with open(fn, 'wb') as f:
        f.write(cab_data)

    # create parent firmware object
    target = request.form['target']
    fw = _create_fw_from_uploaded_file(ufile)
    fw.vendor_id = vendor.vendor_id
    fw.user_id = g.user.user_id
    fw.addr = _get_client_address()
    fw.remote_id = remote.remote_id
    fw.checksum_signed = hashlib.sha1(cab_data).hexdigest()
    fw.is_dirty = True

    # fall back to a version format when unspecified and not semver
    for md in fw.mds:
        if not md.version_format and vendor.version_format and md.version.find('.') == -1:
            md.version_format = vendor.version_format

    metadata = component.get_metadata()
    for md in fw.mds:
        # allows OEM to hide the direct download link on the LVFS
        if 'LVFS::InhibitDownload' in metadata:
            md.inhibit_download = True

        # allows OEM to change the triplet (AA.BB.CCDD) to quad (AA.BB.CC.DD)
        if 'LVFS::VersionFormat' in metadata:
            md.version_format = metadata['LVFS::VersionFormat']

        # allows OEM to specify protocol
        if 'LVFS::UpdateProtocol' in metadata:
            pr = db.session.query(Protocol).\
                    filter(Protocol.value == metadata['LVFS::UpdateProtocol']).first()
            if pr:
                md.protocol_id = pr.protocol_id

    # add to database
    fw.events.append(FirmwareEvent(remote.remote_id, g.user.user_id))
    db.session.add(fw)
    db.session.commit()

    # ensure the test has been added for the firmware type
    ploader.ensure_test_for_fw(fw)

    flash('Uploaded file %s to %s' % (ufile.filename_new, target), 'info')

    # invalidate
    if target == 'embargo':
        remote.is_dirty = True
        g.user.vendor.remote.is_dirty = True
        db.session.commit()

    return redirect(url_for('.firmware_show', firmware_id=fw.firmware_id))

@app.route('/lvfs/upload_hwinfo', methods=['POST'])
def upload_hwinfo():
    """ Upload a hwinfo binary file to the LVFS service without authentication """

    # not correct parameters
    if not 'type' in request.form:
        return _json_error('no type')
    if not 'machine_id' in request.form:
        return _json_error('no machine_id')
    if not 'file' in request.files:
        return _json_error('no file')
    if len(request.form['machine_id']) != 32:
        return _json_error('machine_id %s not valid' % request.form['machine_id'])
    try:
        int(request.form['machine_id'], 16)
    except ValueError as e:
        return _json_error(str(e))

    # check type against defined list
    settings = _get_settings()
    if request.form['type'] not in settings['hwinfo_kinds'].split(','):
        return _json_error('type not valid')

    # read in entire file
    fileitem = request.files['file']
    if not fileitem:
        return _json_error('no file object')
    filebuf = fileitem.read()
    if len(filebuf) > 0x40000:
        return _json_error('file is too large')

    # dump to a file
    hwinfo_dir = os.path.join(app.config['HWINFO_DIR'], request.form['type'])
    if not os.path.exists(hwinfo_dir):
        os.mkdir(hwinfo_dir)
    fn = os.path.join(hwinfo_dir, '%s' % request.form['machine_id'])
    if os.path.exists(fn):
        return _json_error('already reported from this machine-id')
    with open(fn, 'wb') as f:
        f.write(filebuf)
    return _json_success()
