#!/usr/bin/python2
# -*- coding: utf-8 -*-
#
# Copyright (C) 2015-2018 Richard Hughes <richard@hughsie.com>
# Licensed under the GNU General Public License Version 2

import os
import hashlib

from gi.repository import AppStreamGlib
from gi.repository import Gio
from gi.repository import GLib

from app import app, db, ploader

from .hash import _qa_hash
from .models import Firmware, Group
from .util import _get_settings

def _generate_metadata_kind(filename, fws, firmware_baseuri=''):
    """ Generates AppStream metadata of a specific kind """
    store = AppStreamGlib.Store.new()
    store.set_origin('lvfs')
    store.set_api_version(0.9)
    for fw in fws:

        # add each component
        for md in fw.mds:
            component = AppStreamGlib.App.new()
            component.set_id(md.appstream_id)
            component.set_kind(AppStreamGlib.AppKind.FIRMWARE)
            component.set_name(None, md.name)
            component.set_comment(None, md.summary)
            component.set_description(None, md.description)
            if md.url_homepage:
                component.add_url(AppStreamGlib.UrlKind.HOMEPAGE, md.url_homepage)
            component.set_metadata_license(md.metadata_license)
            component.set_project_license(md.project_license)
            component.set_developer_name(None, md.developer_name)

            # add provide
            for guid in md.guids:
                prov = AppStreamGlib.Provide.new()
                prov.set_kind(AppStreamGlib.ProvideKind.FIRMWARE_FLASHED)
                prov.set_value(guid.value)
                component.add_provide(prov)

            # add release
            if md.version:
                rel = AppStreamGlib.Release.new()
                rel.set_version(md.version)
                if md.release_description:
                    rel.set_description(None, md.release_description)
                if md.release_timestamp:
                    rel.set_timestamp(md.release_timestamp)
                rel.checksums = []
                rel.add_location(firmware_baseuri + fw.filename)
                rel.set_size(AppStreamGlib.SizeKind.INSTALLED, md.release_installed_size)
                rel.set_size(AppStreamGlib.SizeKind.DOWNLOAD, md.release_download_size)
                if md.release_urgency:
                    rel.set_urgency(AppStreamGlib.urgency_kind_from_string(md.release_urgency))
                component.add_release(rel)

                # add container checksum
                if fw.checksum:
                    csum = AppStreamGlib.Checksum.new()
                    csum.set_kind(GLib.ChecksumType.SHA1)
                    csum.set_target(AppStreamGlib.ChecksumTarget.CONTAINER)
                    csum.set_value(fw.checksum)
                    csum.set_filename(fw.filename)
                    rel.add_checksum(csum)

                # add content checksum
                if md.checksum_contents:
                    csum = AppStreamGlib.Checksum.new()
                    csum.set_kind(GLib.ChecksumType.SHA1)
                    csum.set_target(AppStreamGlib.ChecksumTarget.CONTENT)
                    csum.set_value(md.checksum_contents)
                    csum.set_filename(md.filename_contents)
                    rel.add_checksum(csum)

            # add screenshot
            if md.screenshot_caption:
                ss = AppStreamGlib.Screenshot.new()
                ss.set_caption(None, md.screenshot_caption)
                if md.screenshot_url:
                    im = AppStreamGlib.Image.new()
                    im.set_url(md.screenshot_url)
                    ss.add_image(im)
                component.add_screenshot(ss)

            # add requires for each allowed vendor_ids
            group = db.session.query(Group).filter(Group.group_id == fw.group_id).first()
            if group and group.vendor_ids:
                req = AppStreamGlib.Require.new()
                req.set_kind(AppStreamGlib.RequireKind.FIRMWARE)
                req.set_value('vendor-id')
                if len(group.vendor_ids) == 1:
                    req.set_compare(AppStreamGlib.RequireCompare.EQ)
                else:
                    req.set_compare(AppStreamGlib.RequireCompare.REGEX)
                req.set_version('|'.join(group.vendor_ids))
                component.add_require(req)

            # add manual firmware or fwupd version requires
            for rq in md.requirements:
                req = AppStreamGlib.Require.new()
                req.set_kind(AppStreamGlib.Require.kind_from_string(rq.kind))
                req.set_value(rq.value)
                if rq.compare:
                    req.set_compare(AppStreamGlib.Require.compare_from_string(rq.compare))
                if rq.version:
                    req.set_version(rq.version)
                component.add_require(req)

            # add component
            store.add_app(component)

    # dump to file
    download_dir = app.config['DOWNLOAD_DIR']
    if not os.path.exists(download_dir):
        os.mkdir(download_dir)
    filename = os.path.join(download_dir, filename)
    store.to_file(Gio.file_new_for_path(filename),
                  AppStreamGlib.NodeToXmlFlags.ADD_HEADER |
                  AppStreamGlib.NodeToXmlFlags.FORMAT_INDENT |
                  AppStreamGlib.NodeToXmlFlags.FORMAT_MULTILINE)

    # inform the plugin loader
    ploader.file_modified(filename)

def _metadata_update_group(group_id):
    """ updates metadata for a specific group_id """

    # get all firmwares in this group
    settings = _get_settings()
    firmwares = db.session.query(Firmware).all()
    firmwares_filtered = []
    for f in firmwares:
        if f.target == 'private':
            continue
        if f.group_id != group_id:
            continue
        firmwares_filtered.append(f)

    # create metadata file for the embargoed firmware
    filename = 'firmware-%s.xml.gz' % _qa_hash(group_id)
    _generate_metadata_kind(filename,
                            firmwares_filtered,
                            firmware_baseuri=settings['firmware_baseuri'])

def _metadata_update_targets(targets):
    """ updates metadata for a specific target """
    firmwares = db.session.query(Firmware).all()
    settings = _get_settings()
    for target in targets:
        firmwares_filtered = []
        for f in firmwares:
            if f.target == 'private':
                continue
            if f.target != target:
                continue
            firmwares_filtered.append(f)
        if target == 'stable':
            _generate_metadata_kind('firmware.xml.gz',
                                    firmwares_filtered,
                                    firmware_baseuri=settings['firmware_baseuri'])
        elif target == 'testing':
            _generate_metadata_kind('firmware-testing.xml.gz',
                                    firmwares_filtered,
                                    firmware_baseuri=settings['firmware_baseuri'])

def _hashfile(afile, hasher, blocksize=65536):
    buf = afile.read(blocksize)
    while len(buf) > 0:
        hasher.update(buf)
        buf = afile.read(blocksize)
    return hasher.hexdigest()

def _metadata_update_pulp():
    """ updates metadata for Pulp """
    files_to_scan = ['firmware.xml.gz', 'firmware.xml.gz.asc']
    for fw in db.session.query(Firmware).all():
        if fw.target != 'stable':
            continue
        files_to_scan.append(fw.filename)

    # for each file in stable plus metadata
    data = []
    download_dir = app.config['DOWNLOAD_DIR']
    for f in files_to_scan:
        fn = os.path.join(download_dir, f)
        if not os.path.exists(fn):
            continue

        # filename,sha256,size
        sha256 = _hashfile(open(fn, 'rb'), hashlib.sha256())
        fn_sz = os.path.getsize(fn)
        data.append('%s,%s,%i\n' % (f, sha256, fn_sz))

    # write file
    filename = os.path.join(download_dir, 'PULP_MANIFEST')
    f = open(filename, 'w')
    f.writelines(data)
    f.close()
