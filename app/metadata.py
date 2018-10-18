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

from app import app, db

from .models import Firmware, Vendor
from .util import _get_settings

def _generate_metadata_kind(filename, fws, firmware_baseuri=''):
    """ Generates AppStream metadata of a specific kind """
    store = AppStreamGlib.Store.new()
    store.set_origin('lvfs')
    store.set_api_version(0.9)

    components = {}
    for fw in fws:

        # add each component
        for md in fw.mds:
            if md.appstream_id not in components:
                component = AppStreamGlib.App.new()
                component.set_trust_flags(AppStreamGlib.AppTrustFlags.CHECK_DUPLICATES)
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
                component.set_priority(md.priority)
                components[md.appstream_id] = component
            else:
                component = components[md.appstream_id]

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
                if fw.checksum_signed:
                    csum = AppStreamGlib.Checksum.new()
                    csum.set_kind(GLib.ChecksumType.SHA1)
                    csum.set_target(AppStreamGlib.ChecksumTarget.CONTAINER)
                    csum.set_value(fw.checksum_signed)
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
            vendor = db.session.query(Vendor).filter(Vendor.vendor_id == fw.vendor_id).first()
            if vendor and vendor.restrictions:
                vendor_ids = []
                for res in vendor.restrictions:
                    vendor_ids.append(res.value)
                req = AppStreamGlib.Require.new()
                req.set_kind(AppStreamGlib.RequireKind.FIRMWARE)
                req.set_value('vendor-id')
                if len(vendor_ids) == 1:
                    req.set_compare(AppStreamGlib.RequireCompare.EQ)
                else:
                    req.set_compare(AppStreamGlib.RequireCompare.REGEX)
                req.set_version('|'.join(vendor_ids))
                component.add_require(req)

            # add manual firmware or fwupd version requires
            for rq in md.requirements:
                if rq.kind == 'hardware':
                    continue
                req = AppStreamGlib.Require.new()
                req.set_kind(AppStreamGlib.Require.kind_from_string(rq.kind))
                if rq.value:
                    req.set_value(rq.value)
                if rq.compare:
                    req.set_compare(AppStreamGlib.Require.compare_from_string(rq.compare))
                if rq.version:
                    req.set_version(rq.version)
                component.add_require(req)

            # add hardware requirements
            rq_hws = []
            for rq in md.requirements:
                if rq.kind == 'hardware':
                    rq_hws.append(rq.value)
            if rq_hws:
                req = AppStreamGlib.Require.new()
                req.set_kind(AppStreamGlib.RequireKind.HARDWARE)
                req.set_value('|'.join(rq_hws))
                component.add_require(req)

            # add any shared metadata
            if md.inhibit_download:
                component.add_metadata('LVFS::InhibitDownload')
            if md.version_format:
                component.add_metadata('LVFS::VersionFormat', md.version_format)

    # add components
    for appstream_id in components:
        store.add_app(components[appstream_id])

    # dump to file
    store.to_file(Gio.file_new_for_path(filename),
                  AppStreamGlib.NodeToXmlFlags.ADD_HEADER |
                  AppStreamGlib.NodeToXmlFlags.FORMAT_INDENT |
                  AppStreamGlib.NodeToXmlFlags.FORMAT_MULTILINE)

def _metadata_update_targets(remotes):
    """ updates metadata for a specific target """
    fws = db.session.query(Firmware).all()
    settings = _get_settings()

    # set destination path from app config
    download_dir = app.config['DOWNLOAD_DIR']
    if not os.path.exists(download_dir):
        os.mkdir(download_dir)

    # create metadata for each remote
    for r in remotes:
        fws_filtered = []
        for fw in fws:
            if fw.is_deleted:
                continue
            if not fw.signed_timestamp:
                continue
            if r.check_fw(fw):
                fws_filtered.append(fw)
        _generate_metadata_kind(os.path.join(download_dir, r.filename),
                                fws_filtered,
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
        if fw.remote.name != 'stable':
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
