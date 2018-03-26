#!/usr/bin/python2
# -*- coding: utf-8 -*-
#
# Copyright (C) 2015-2018 Richard Hughes <richard@hughsie.com>
# Licensed under the GNU General Public License Version 2
#
# pylint: disable=too-many-locals

from __future__ import print_function

import os
import datetime
import hashlib

from gi.repository import AppStreamGlib
from gi.repository import Gio

from flask import request, flash, url_for, redirect, render_template, g
from flask_login import login_required

from app import app, db, ploader

from .models import Firmware, Component, Requirement, Guid, FirmwareEvent, Vendor, Remote, Agreement
from .uploadedfile import UploadedFile, FileTooLarge, FileTooSmall, FileNotSupported, MetadataInvalid
from .util import _get_client_address, _get_settings
from .util import _error_internal, _error_permission_denied

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
        return render_template('upload.html', vendor_ids=vendor_ids)

    # verify the user can upload
    if not _user_can_upload(g.user):
        return _error_permission_denied('User has not signed legal agreement')

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
        remote = g.user.vendor.remote
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
    open(fn, 'wb').write(cab_data)

    # inform the plugin loader
    ploader.file_modified(fn)

    # create parent firmware object
    target = request.form['target']
    fw = Firmware()
    fw.vendor_id = g.user.vendor_id
    fw.user_id = g.user.user_id
    fw.addr = _get_client_address()
    fw.filename = ufile.filename_new
    fw.checksum_upload = ufile.checksum_upload
    fw.remote_id = remote.remote_id
    fw.checksum_signed = hashlib.sha1(cab_data).hexdigest()
    if ufile.version_display:
        fw.version_display = ufile.version_display

    # this allows an OEM to hide the direct download link on the LVFS
    if 'LVFS::InhibitDownload' in ufile.metadata:
        fw.inhibit_download = True

    # create child metadata object for the component
    for component in ufile.get_components():
        md = Component()
        md.appstream_id = component.get_id()
        md.name = unicode(component.get_name())
        md.summary = unicode(component.get_comment())
        md.developer_name = unicode(component.get_developer_name())
        md.metadata_license = component.get_metadata_license()
        md.project_license = component.get_project_license()
        md.url_homepage = unicode(component.get_url_item(AppStreamGlib.UrlKind.HOMEPAGE))
        md.description = unicode(component.get_description())

        # add manually added keywords
        for keyword in component.get_keywords():
            md.add_keywords_from_string(unicode(keyword), priority=5)

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
        md.release_description = unicode(rel.get_description())
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
                md.screenshot_url = unicode(im.get_url())

        # from the content checksum
        csum = rel.get_checksum_by_target(AppStreamGlib.ChecksumTarget.CONTENT)
        md.checksum_contents = csum.get_value()
        md.filename_contents = csum.get_filename()

        fw.mds.append(md)

    # add to database
    fw.events.append(FirmwareEvent(remote.remote_id, g.user.user_id))
    db.session.add(fw)
    db.session.commit()
    flash('Uploaded file %s to %s' % (ufile.filename_new, target), 'info')

    # invalidate
    if target == 'embargo':
        remote.is_dirty = True
        db.session.commit()

    return redirect(url_for('.firmware_show', firmware_id=fw.firmware_id))
