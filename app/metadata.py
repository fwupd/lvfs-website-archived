#!/usr/bin/python2
# -*- coding: utf-8 -*-
#
# Copyright (C) 2015 Richard Hughes <richard@hughsie.com>
# Licensed under the GNU General Public License Version 2

import os
import hashlib
import appstream

from app import app, db

from .hash import _qa_hash
from .util import _create_affidavit

def _generate_metadata_kind(filename, items, firmware_baseurl='',
                            affidavit=None):
    """ Generates AppStream metadata of a specific kind """
    store = appstream.Store('lvfs')
    for item in items:

        # add each component
        for md in item.mds:
            component = appstream.Component()
            component.id = md.cid
            component.kind = 'firmware'
            component.name = md.name
            component.summary = md.summary
            component.description = md.description
            if md.url_homepage:
                component.urls['homepage'] = md.url_homepage
            component.metadata_license = md.metadata_license
            component.project_license = md.project_license
            component.developer_name = md.developer_name

            # add provide
            for guid in md.guids:
                prov = appstream.Provide()
                prov.kind = 'firmware-flashed'
                prov.value = guid
                component.add_provide(prov)

            # add release
            if md.version:
                rel = appstream.Release()
                rel.version = md.version
                rel.description = md.release_description
                if md.release_timestamp:
                    rel.timestamp = md.release_timestamp
                rel.checksums = []
                rel.location = firmware_baseurl + item.filename
                rel.size_installed = md.release_installed_size
                rel.size_download = md.release_download_size
                rel.urgency = md.release_urgency
                component.add_release(rel)

                # add container checksum
                if md.checksum_container:
                    csum = appstream.Checksum()
                    csum.target = 'container'
                    csum.value = md.checksum_container
                    csum.filename = item.filename
                    rel.add_checksum(csum)

                # add content checksum
                if md.checksum_contents:
                    csum = appstream.Checksum()
                    csum.target = 'content'
                    csum.value = md.checksum_contents
                    csum.filename = md.filename_contents
                    rel.add_checksum(csum)

            # add screenshot
            if md.screenshot_caption:
                ss = appstream.Screenshot()
                ss.caption = md.screenshot_caption
                if md.screenshot_url:
                    im = appstream.Image()
                    im.url = md.screenshot_url
                    ss.add_image(im)
                component.add_screenshot(ss)

            # add requires for each allowed vendor_ids
            group = db.groups.get_item(item.group_id)
            if group and group.vendor_ids:
                req = appstream.Require()
                req.kind = 'firmware'
                req.value = 'vendor-id'
                if len(group.vendor_ids) == 1:
                    req.compare = 'eq'
                else:
                    req.compare = 'regex'
                req.version = '|'.join(group.vendor_ids)
                component.add_require(req)

            # add manual firmware or fwupd version requires
            for fwreq in md.requirements:
                req = appstream.Require()
                req.kind = fwreq.kind
                req.value = fwreq.value
                req.compare = fwreq.compare
                req.version = fwreq.version
                component.add_require(req)

            # add component
            store.add(component)

    # dump to file
    download_dir = app.config['DOWNLOAD_DIR']
    if not os.path.exists(download_dir):
        os.mkdir(download_dir)
    filename = os.path.join(download_dir, filename)
    store.to_file(filename)

    # generate and upload the detached signature
    if affidavit:
        blob = open(filename, 'rb').read()
        blob_asc = affidavit.create(blob)
        filename_asc = filename + '.asc'
        with open(filename_asc,'w') as f:
            f.write(blob_asc)

def _metadata_update_group(group_id):
    """ updates metadata for a specific group_id """

    # get all firmwares in this group
    settings = db.settings.get_all()
    firmwares = db.firmware.get_all()
    firmwares_filtered = []
    for f in firmwares:
        if f.target == 'private':
            continue
        if f.group_id != group_id:
            continue
        firmwares_filtered.append(f)

    # create metadata file for the embargoed firmware
    affidavit = _create_affidavit()
    filename = 'firmware-%s.xml.gz' % _qa_hash(group_id)
    _generate_metadata_kind(filename,
                            firmwares_filtered,
                            firmware_baseurl=settings['firmware_baseurl'],
                            affidavit=affidavit)

def _metadata_update_targets(targets):
    """ updates metadata for a specific target """
    affidavit = _create_affidavit()
    firmwares = db.firmware.get_all()
    settings = db.settings.get_all()
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
                                    firmware_baseurl=settings['firmware_baseurl'],
                                    affidavit=affidavit)
        elif target == 'testing':
            _generate_metadata_kind('firmware-testing.xml.gz',
                                    firmwares_filtered,
                                    firmware_baseurl=settings['firmware_baseurl'],
                                    affidavit=affidavit)

def _hashfile(afile, hasher, blocksize=65536):
    buf = afile.read(blocksize)
    while len(buf) > 0:
        hasher.update(buf)
        buf = afile.read(blocksize)
    return hasher.hexdigest()

def _metadata_update_pulp():
    """ updates metadata for Pulp """
    items = db.firmware.get_all()
    files_to_scan = []
    files_to_scan.append('firmware.xml.gz')
    files_to_scan.append('firmware.xml.gz.asc')
    for item in items:
        if item.target != 'stable':
            continue
        files_to_scan.append(item.filename)

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
