#!/usr/bin/python2
# -*- coding: utf-8 -*-
#
# Copyright (C) 2015-2018 Richard Hughes <richard@hughsie.com>
# Licensed under the GNU General Public License Version 2
#
# pylint: disable=singleton-comparison,wrong-import-position

from __future__ import print_function

import os
import sys
import hashlib
import datetime

import gi
gi.require_version('AppStreamGlib', '1.0')
from gi.repository import AppStreamGlib
gi.require_version('GCab', '1.0')
from gi.repository import GCab
from gi.repository import Gio
from gi.repository import GLib

import app as application
from app import db, ploader

from app.models import Remote, Firmware
from app.metadata import _metadata_update_targets, _metadata_update_pulp
from app.util import _archive_get_files_from_glob, _get_dirname_safe, _event_log
from app.pluginloader import PluginError

# make compatible with Flask
app = application.app

def _regenerate_and_sign_metadata():

    # get list of dirty remotes
    remotes = []
    for r in db.session.query(Remote).all():
        if r.is_signed and r.is_dirty:
            remotes.append(r)

    # nothing to do
    if not len(remotes):
        return

    # update everything required
    for r in remotes:
        print('Updating: %s' % r.name)
    _metadata_update_targets(remotes)
    for r in remotes:
        if r.name == 'stable':
            _metadata_update_pulp()

    # sign and sync
    download_dir = app.config['DOWNLOAD_DIR']
    for r in remotes:
        ploader.file_modified(os.path.join(download_dir, r.filename))

    # mark as no longer dirty
    for r in remotes:
        r.is_dirty = False
        db.session.commit()

    # drop caches in other sessions
    db.session.expire_all()

    # log what we did
    for r in remotes:
        _event_log('Signed metadata %s' % r.name)

def _sign_md(cfarchive, cf):
    # parse each metainfo file
    try:
        component = AppStreamGlib.App.new()
        component.parse_data(cf.get_bytes(), AppStreamGlib.AppParseFlags.NONE)
    except Exception as e:
        raise NotImplementedError('Invalid metadata in %s: %s' % (cf.get_name(), str(e)))

    # sign each firmware
    release = component.get_release_default()
    csum = release.get_checksum_by_target(AppStreamGlib.ChecksumTarget.CONTENT)
    if not csum:
        csum = AppStreamGlib.Checksum.new()
        csum.set_filename('firmware.bin')

    # get the filename including the correct dirname
    fn = os.path.join(_get_dirname_safe(cf.get_name()), csum.get_filename())
    cfs = _archive_get_files_from_glob(cfarchive, fn)
    if not cfs:
        raise NotImplementedError('no %s firmware found in %s' % (fn, cf.get_name()))

    # sign the firmware.bin file
    ploader.archive_sign(cfarchive, cfs[0])

def _sign_fw(fw):

    # load the .cab file
    download_dir = app.config['DOWNLOAD_DIR']
    fn = os.path.join(download_dir, fw.filename)
    try:
        data = open(fn, 'rb').read()
    except IOError as e:
        raise NotImplementedError('cannot read %s: %s' % (fn, str(e)))
    istream = Gio.MemoryInputStream.new_from_bytes(GLib.Bytes.new(data))
    cfarchive = GCab.Cabinet.new()
    cfarchive.load(istream)
    cfarchive.extract(None)

    # look for each metainfo file
    cfs = _archive_get_files_from_glob(cfarchive, '*.metainfo.xml')
    if len(cfs) == 0:
        raise NotImplementedError('no .metadata.xml files in %s' % fn)

    # parse each MetaInfo file
    print('Signing: %s' % fn)
    for cf in cfs:
        _sign_md(cfarchive, cf)

    # save the new archive
    ostream = Gio.MemoryOutputStream.new_resizable()
    cfarchive.write_simple(ostream)
    cab_data = Gio.MemoryOutputStream.steal_as_bytes(ostream).get_data()

    # overwrite old file
    open(fn, 'wb').write(cab_data)

    # inform the plugin loader
    ploader.file_modified(fn)

    # update the database
    fw.checksum_signed = hashlib.sha1(cab_data).hexdigest()
    fw.signed_timestamp = datetime.datetime.utcnow()
    db.session.commit()

def _regenerate_and_sign_firmware():

    # find all unsigned firmware
    fws = db.session.query(Firmware).\
                        filter(Firmware.signed_timestamp == None).all()
    if not len(fws):
        return

    # sign each firmware in each file
    for fw in fws:
        if fw.is_deleted:
            continue
        print('Signing firmware %u...' % fw.firmware_id)
        _sign_fw(fw)
        _event_log('Signed firmware %s' % fw.firmware_id)

    # drop caches in other sessions
    db.session.expire_all()

def _purge_old_deleted_firmware():

    # find all unsigned firmware
    for fw in db.session.query(Firmware).all():
        if fw.is_deleted and fw.target_duration > datetime.timedelta(days=30*6):
            print('Deleting %s as age %s' % (fw.filename, fw.target_duration))
            path = os.path.join(app.config['RESTORE_DIR'], fw.filename)
            if os.path.exists(path):
                os.remove(path)
            db.session.delete(fw)

    # all done
    db.session.commit()

def _check_firmware():

    # ensure the assay has been added for the firmware type
    for fw in db.session.query(Firmware).all():
        if fw.is_deleted:
            continue
        for md in fw.mds:
            ploader.ensure_assay_for_md(md)

        # process each assay
        for md in fw.mds:
            for assay in md.assays:
                if assay.ended_ts:
                    continue
                if assay.started_ts:
                    _event_log('Assay %s already running on %s, ignoring' % (assay.plugin_id, md.component_id))
                    continue
                plugin = ploader.get_by_id(assay.plugin_id)
                if not plugin:
                    _event_log('No plugin %s' % assay.plugin_id)
                    assay.ended_ts = datetime.datetime.utcnow()
                    continue
                if not hasattr(plugin, 'run_assay_on_md'):
                    _event_log('No run_assay_on_md in %s' % assay.plugin_id)
                    assay.ended_ts = datetime.datetime.utcnow()
                    continue
                try:
                    assay.started_ts = datetime.datetime.utcnow()
                    _event_log('Running assay %s on component %s' % (assay.plugin_id, md.component_id))
                    plugin.run_assay_on_md(assay, md)
                    assay.ended_ts = datetime.datetime.utcnow()
                    # don't leave a failed task running
                    db.session.commit()
                except PluginError as e:
                    _event_log('Plugin %s failed for run_assay_on_md(): %s' % (plugin.id, str(e)))

    # all done
    db.session.commit()

if __name__ == '__main__':

    if len(sys.argv) < 2:
        print('Usage: %s [metadata] [firmware]' % sys.argv[0])
        sys.exit(1)

    # regenerate and sign firmware then metadata
    if 'firmware' in sys.argv:
        try:
            with app.test_request_context():
                _regenerate_and_sign_firmware()
        except NotImplementedError as e:
            print(str(e))
            sys.exit(1)
    if 'metadata' in sys.argv:
        try:
            with app.test_request_context():
                _regenerate_and_sign_metadata()
        except NotImplementedError as e:
            print(str(e))
            sys.exit(1)
    if 'purgedelete' in sys.argv:
        try:
            with app.test_request_context():
                _purge_old_deleted_firmware()
        except NotImplementedError as e:
            print(str(e))
            sys.exit(1)
    if 'fwchecks' in sys.argv:
        try:
            with app.test_request_context():
                _check_firmware()
        except NotImplementedError as e:
            print(str(e))
            sys.exit(1)

    # success
    sys.exit(0)
