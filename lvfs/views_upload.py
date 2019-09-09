#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2015-2018 Richard Hughes <richard@hughsie.com>
#
# SPDX-License-Identifier: GPL-2.0+
#
# pylint: disable=too-many-locals

import os
import datetime
import hashlib

from flask import request, flash, url_for, redirect, render_template, g
from flask_login import login_required

from lvfs import app, db, ploader, csrf

from .models import Firmware, FirmwareEvent, Vendor, Remote, Agreement
from .models import Affiliation, Protocol, Category, Component
from .uploadedfile import UploadedFile, FileTooLarge, FileTooSmall, FileNotSupported, MetadataInvalid
from .util import _get_client_address, _get_settings, _fix_component_name
from .util import _error_internal
from .util import _json_success, _json_error
from .views_firmware import _firmware_delete

def _get_plugin_metadata_for_uploaded_file(ufile):
    settings = _get_settings()
    metadata = {}
    metadata['$DATE$'] = datetime.datetime.now().replace(microsecond=0).isoformat()
    metadata['$FWUPD_MIN_VERSION$'] = ufile.fwupd_min_version
    metadata['$CAB_FILENAME$'] = ufile.fw.filename
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

def _upload_firmware():

    # verify the user can upload
    if not _user_can_upload(g.user):
        flash('User has not signed legal agreement', 'danger')
        return redirect(url_for('.dashboard'))

    # used a custom vendor_id
    if 'vendor_id' in request.form:
        try:
            vendor_id = int(request.form['vendor_id'])
        except ValueError as e:
            flash('Failed to upload file: Specified vendor ID %s invalid' % request.form['vendor_id'], 'warning')
            return redirect(url_for('.upload_firmware'))
        vendor = db.session.query(Vendor).filter(Vendor.vendor_id == vendor_id).first()
        if not vendor:
            flash('Failed to upload file: Specified vendor ID not found', 'warning')
            return redirect(url_for('.upload_firmware'))
    else:
        vendor = g.user.vendor

    # security check
    if not vendor.check_acl('@upload'):
        flash('Permission denied: Failed to upload file for vendor: '
              'User with vendor %s cannot upload to vendor %s' %
              (g.user.vendor.group_id, vendor.group_id), 'warning')
        return redirect(url_for('.upload_firmware'))

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

    # if the vendor has uploaded a lot of firmware don't start changing the rules
    is_strict = len(vendor.fws) < 500

    # load in the archive
    fileitem = request.files['file']
    if not fileitem:
        return _error_internal('No file object')
    try:
        ufile = UploadedFile(is_strict=is_strict)
        for cat in db.session.query(Category):
            ufile.category_map[cat.value] = cat.category_id
        for pro in db.session.query(Protocol):
            ufile.protocol_map[pro.value] = pro.protocol_id
        ufile.parse(os.path.basename(fileitem.filename), fileitem.read())
    except (FileTooLarge, FileTooSmall, FileNotSupported, MetadataInvalid) as e:
        flash('Failed to upload file: ' + str(e), 'danger')
        return redirect(request.url)

    # check the file does not already exist
    fw = db.session.query(Firmware).filter(Firmware.checksum_upload == ufile.fw.checksum_upload).first()
    if fw:
        if fw.check_acl('@view'):
            flash('Failed to upload file: A file with hash %s already exists' % fw.checksum_upload, 'warning')
            return redirect('/lvfs/firmware/%s' % fw.firmware_id)
        flash('Failed to upload file: Another user has already uploaded this firmware', 'warning')
        return redirect(url_for('.upload_firmware'))

    # check the guid and version does not already exist
    fws = db.session.query(Firmware).all()
    fws_already_exist = []
    for md in ufile.fw.mds:
        provides_value = md.guids[0].value
        fw = _filter_fw_by_id_guid_version(fws,
                                           md.appstream_id,
                                           provides_value,
                                           md.version)
        if fw:
            fws_already_exist.append(fw)

    # all the components existed, so build an error out of all the versions
    if len(fws_already_exist) == len(ufile.fw.mds):
        if g.user.is_robot and 'auto-delete' in request.form:
            for fw in fws_already_exist:
                if fw.remote.is_public:
                    flash('Firmware {} cannot be autodeleted as is in remote {}'.format(
                        fw.firmware_id, fw.remote.name), 'danger')
                    return redirect(url_for('.upload_firmware'))
                if fw.user.user_id != g.user.user_id:
                    flash('Firmware was not uploaded by this user', 'danger')
                    return redirect(url_for('.upload_firmware'))
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
    for umd in ufile.fw.mds:
        new_guids = [guid.value for guid in umd.guids]
        for md in db.session.query(Component).\
                        filter(Component.appstream_id == umd.appstream_id):
            if md.fw.is_deleted:
                continue
            for old_guid in [guid.value for guid in md.guids]:
                if old_guid in new_guids:
                    continue
                fw_str = str(md.fw.firmware_id)
                if g.user.is_qa or g.user.is_robot:
                    flash('Firmware drops GUID {} previously supported '
                          'in firmware {}'.format(old_guid, fw_str), 'warning')
                else:
                    flash('Firmware would drop GUID {} previously supported '
                          'in firmware {}'.format(old_guid, fw_str), 'danger')
                    return redirect(request.url)

    # allow plugins to copy any extra files from the source archive
    for cffile in ufile.cabarchive_upload.values():
        ploader.archive_copy(ufile.cabarchive_repacked, cffile)

    # allow plugins to add files
    ploader.archive_finalize(ufile.cabarchive_repacked,
                             _get_plugin_metadata_for_uploaded_file(ufile))

    # dump to a file
    download_dir = app.config['DOWNLOAD_DIR']
    if not os.path.exists(download_dir):
        os.mkdir(download_dir)
    fn = os.path.join(download_dir, ufile.fw.filename)
    cab_data = ufile.cabarchive_repacked.save(compress=True)
    with open(fn, 'wb') as f:
        f.write(cab_data)

    # create parent firmware object
    settings = _get_settings()
    target = request.form['target']
    fw = ufile.fw
    fw.vendor = vendor
    fw.user = g.user
    fw.addr = _get_client_address()
    fw.remote = remote
    fw.checksum_signed = hashlib.sha1(cab_data).hexdigest()
    fw.checksum_pulp = hashlib.sha256(cab_data).hexdigest()
    fw.is_dirty = True
    fw.failure_minimum = settings['default_failure_minimum']
    fw.failure_percentage = settings['default_failure_percentage']

    # fix name
    for md in fw.mds:
        name_fixed = _fix_component_name(md.name, md.developer_name_display)
        if name_fixed != md.name:
            flash('Fixed component name from "%s" to "%s"' % (md.name, name_fixed), 'warning')
            md.name = name_fixed

    # fall back to a version format when unspecified and not semver
    for md in fw.mds:
        if not md.version_format and vendor.version_format and md.version.find('.') == -1:
            md.version_format = vendor.version_format

    # add to database
    fw.events.append(FirmwareEvent(remote.remote_id, g.user.user_id))
    db.session.add(fw)
    db.session.commit()

    # ensure the test has been added for the firmware type
    ploader.ensure_test_for_fw(fw)

    flash('Uploaded file %s to %s' % (ufile.fw.filename, target), 'info')

    # invalidate
    if target == 'embargo':
        remote.is_dirty = True
        g.user.vendor.remote.is_dirty = True
        db.session.commit()

    return redirect(url_for('.firmware_show', firmware_id=fw.firmware_id))

@app.route('/lvfs/upload', methods=['GET', 'POST'])
@login_required
@csrf.exempt
def upload_robot():
    """ Upload a .cab file to the LVFS service from a robot user """

    # old URL being used
    if request.method != 'POST':
        return redirect(url_for('.upload_firmware'))

    # check is robot
    if not g.user.is_robot:
        flash('Not a robot user, please try again')
        return redirect(url_for('.upload_firmware'))

    # continue with form data
    return _upload_firmware()

@app.route('/lvfs/upload_firmware', methods=['GET', 'POST'])
@login_required
def upload_firmware():
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
        return render_template('upload.html',
                               category='firmware',
                               vendor_ids=vendor_ids,
                               affiliations=affiliations)

    # continue with form data
    return _upload_firmware()

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
