#!/usr/bin/python2
# -*- coding: utf-8 -*-
#
# Copyright (C) 2015-2018 Richard Hughes <richard@hughsie.com>
# Licensed under the GNU General Public License Version 2

from __future__ import print_function

import os
import datetime
import hashlib

from gi.repository import AppStreamGlib
from gi.repository import Gio

from flask import session, request, flash, url_for, redirect, render_template, g
from flask_login import login_required

from app import app, db, ploader

from .models import Firmware, Component, Requirement, UserCapability, Guid, Group, FirmwareEvent
from .uploadedfile import UploadedFile, FileTooLarge, FileTooSmall, FileNotSupported, MetadataInvalid
from .util import _get_client_address, _get_settings
from .util import _error_internal, _error_permission_denied
from .metadata import _metadata_update_group, _metadata_update_targets, _metadata_update_pulp

def _get_plugin_metadata_for_uploaded_file(ufile):
    settings = _get_settings()
    metadata = {}
    metadata['$DATE$'] = datetime.datetime.now().replace(microsecond=0).isoformat()
    metadata['$FWUPD_MIN_VERSION$'] = ufile.fwupd_min_version
    metadata['$CAB_FILENAME$'] = ufile.filename_new
    metadata['$FIRMWARE_BASEURI$'] = settings['firmware_baseuri']
    return metadata

@app.route('/lvfs/upload', methods=['GET', 'POST'])
@login_required
def upload():
    """ Upload a .cab file to the LVFS service """

    # only accept form data
    if request.method != 'POST':
        if 'username' not in session:
            return redirect(url_for('.index'))
        vendor_ids = []
        group = db.session.query(Group).filter(Group.group_id == g.user.group_id).first()
        if group and len(group.vendor_ids):
            vendor_ids = group.vendor_ids
        return render_template('upload.html', vendor_ids=vendor_ids)

    # not correct parameters
    if not 'target' in request.form:
        return _error_internal('No target')
    if not 'file' in request.files:
        return _error_internal('No file')
    if request.form['target'] not in ['private', 'embargo', 'testing', 'stable']:
        return _error_internal('Target not valid')

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
        flash('Failed to upload file: ' + str(e), 'danger')
        return redirect(request.url)

    # check the file does not already exist
    fw = db.session.query(Firmware).filter(Firmware.checksum_upload == ufile.checksum_upload).first()
    if fw:
        if g.user.check_for_firmware(fw):
            flash('Failed to upload file: A file with hash %s already exists' % fw.checksum_upload, 'warning')
            return redirect('/lvfs/firmware/%s' % fw.firmware_id)
        flash('Failed to upload file: Another user has already uploaded this firmware', 'warning')
        return redirect('/lvfs/upload')

    # check the guid and version does not already exist
    fws = db.session.query(Firmware).all()
    for component in ufile.get_components():
        provides_value = component.get_provides()[0].get_value()
        release_default = component.get_release_default()
        release_version = release_default.get_version()
        for fw in fws:
            for md in fw.mds:
                for guid in md.guids:
                    if guid.value == provides_value and md.version == release_version:
                        flash('Failed to upload file: A firmware file for '
                              'version %s already exists' % release_version, 'danger')
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
                if md.appstream_id != component.get_id():
                    continue
                for old_guid in md.guids:
                    if not old_guid.value in new_guids:
                        flash('Firmware %s dropped a GUID previously '
                              'supported %s' % (md.appstream_id, old_guid), 'danger')
                        return redirect(request.url)

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
    open(fn, 'wb').write(cab_data)

    # inform the plugin loader
    ploader.file_modified(fn)

    # create parent firmware object
    target = request.form['target']
    fw = Firmware()
    fw.group_id = g.user.group_id
    fw.username = g.user.username
    fw.addr = _get_client_address()
    fw.filename = ufile.filename_new
    fw.checksum_upload = ufile.checksum_upload
    fw.target = target
    fw.checksum_signed = hashlib.sha1(cab_data).hexdigest()
    if ufile.version_display:
        fw.version_display = ufile.version_display

    # create child metadata object for the component
    for component in ufile.get_components():
        md = Component()
        md.appstream_id = component.get_id()
        md.name = component.get_name()
        md.summary = component.get_comment()
        md.developer_name = component.get_developer_name()
        md.metadata_license = component.get_metadata_license()
        md.project_license = component.get_project_license()
        md.url_homepage = component.get_url_item(AppStreamGlib.UrlKind.HOMEPAGE)
        md.description = component.get_description()

        # from the provide
        for prov in component.get_provides():
            if prov.get_kind() != AppStreamGlib.ProvideKind.FIRMWARE_FLASHED:
                continue
            md.guids.append(Guid(md.component_id, prov.get_value()))

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
            rq = Requirement(md.component_id,
                             AppStreamGlib.Require.kind_to_string(req.get_kind()),
                             req.get_value(),
                             AppStreamGlib.Require.compare_to_string(req.get_compare()),
                             req.get_version())
            md.requirements.append(rq)

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
    fw.events.append(FirmwareEvent(target, g.user.user_id))
    db.session.add(fw)
    db.session.commit()
    flash('Uploaded file %s to %s' % (ufile.filename_new, target), 'info')

    # ensure up to date
    if target == 'embargo':
        _metadata_update_group(fw.group_id)
    if target == 'stable':
        _metadata_update_targets(['stable', 'testing'])
        _metadata_update_pulp()
    elif target == 'testing':
        _metadata_update_targets(['testing'])

    return redirect(url_for('.firmware_show', firmware_id=fw.firmware_id))
