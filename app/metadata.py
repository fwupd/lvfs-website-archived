#!/usr/bin/python2
# -*- coding: utf-8 -*-
#
# Copyright (C) 2015-2018 Richard Hughes <richard@hughsie.com>
# Licensed under the GNU General Public License Version 2

import os
import hashlib
from lxml import etree as ET

from app import app, db

from .models import Firmware, Vendor
from .util import _get_settings, _xml_from_markdown

def _generate_metadata_kind(filename, fws, firmware_baseuri=''):
    """ Generates AppStream metadata of a specific kind """

    root = ET.Element('components')
    root.set('origin', 'lvfs')
    root.set('version', '0.9')

    # build a map of appstream_id:mds
    components = {}
    for fw in sorted(fws, key=lambda fw: fw.mds[0].appstream_id):
        for md in fw.mds:
            if md.appstream_id not in components:
                components[md.appstream_id] = [md]
            else:
                mds = components[md.appstream_id]
                mds.append(md)

    # process each component in ID order
    for appstream_id in sorted(components):
        mds = components[appstream_id]
        mds.sort(key=lambda md: md.release_timestamp, reverse=True)

        # assume all the components have the same parent firmware information
        md = mds[0]
        component = ET.SubElement(root, 'component')
        component.set('type', 'firmware')
        ET.SubElement(component, 'id').text = md.appstream_id
        ET.SubElement(component, 'name').text = md.name
        ET.SubElement(component, 'summary').text = md.summary
        ET.SubElement(component, 'developer_name').text = md.developer_name
        if md.description:
            component.append(_xml_from_markdown(md.description))
        ET.SubElement(component, 'project_license').text = md.project_license
        if md.url_homepage:
            child = ET.SubElement(component, 'url')
            child.set('type', 'homepage')
            child.text = md.url_homepage
        for md in mds:
            if md.priority:
                component.set('priority', str(md.priority))

        # add requires for each allowed vendor_ids
        elements = {}
        for md in mds:
            vendor = db.session.query(Vendor).filter(Vendor.vendor_id == md.fw.vendor_id).first()
            if not vendor:
                continue
            if not vendor.restrictions:
                continue

            # allow specifying more than one ID
            vendor_ids = []
            for res in vendor.restrictions:
                vendor_ids.append(res.value)
            child = ET.Element('firmware')
            child.text = 'vendor-id'
            if len(vendor_ids) == 1:
                child.set('compare', 'eq')
            else:
                child.set('compare', 'regex')
            child.set('version', '|'.join(vendor_ids))
            elements['vendor-id'] = child

        # add requires for <firmware> or fwupd version
        for md in mds:
            for rq in md.requirements:
                if rq.kind == 'hardware':
                    continue
                child = ET.Element(rq.kind)
                if rq.value:
                    child.text = rq.value
                if rq.compare:
                    child.set('compare', rq.compare)
                if rq.version:
                    child.set('version', rq.version)
                elements[rq.kind + str(rq.value)] = child

        # add a single requirement for <hardware>
        rq_hws = []
        for md in mds:
            for rq in md.requirements:
                if rq.kind == 'hardware':
                    rq_hws.append(rq.value)
        if rq_hws:
            child = ET.Element('hardware')
            child.text = '|'.join(rq_hws)
            elements['hardware'] = child

        # requires shared by all releases
        if elements:
            parent = ET.SubElement(component, 'requires')
            for key in elements:
                parent.append(elements[key])

        # screenshot shared by all releases
        elements = {}
        for md in mds:
            if not md.screenshot_url and not md.screenshot_caption:
                continue
            # try to dedupe using the URL and then the caption
            key = md.screenshot_url
            if not key:
                key = md.screenshot_caption
            if key not in elements:
                child = ET.Element('screenshot')
                if not elements:
                    child.set('type', 'default')
                if md.screenshot_caption:
                    ET.SubElement(child, 'caption').text = md.screenshot_caption
                if md.screenshot_url:
                    ET.SubElement(child, 'image').text = md.screenshot_url
                elements[key] = child
        if elements:
            parent = ET.SubElement(component, 'screenshots')
            for key in elements:
                parent.append(elements[key])

        # add each release
        releases = ET.SubElement(component, 'releases')
        for md in mds:
            if not md.version:
                continue
            rel = ET.SubElement(releases, 'release')
            if md.release_timestamp:
                rel.set('timestamp', str(md.release_timestamp))
            if md.release_urgency and md.release_urgency != 'unknown':
                rel.set('urgency', md.release_urgency)
            if md.version:
                rel.set('version', md.version)
            ET.SubElement(rel, 'location').text = firmware_baseuri + md.fw.filename

            # add container checksum
            if md.fw.checksum_signed:
                csum = ET.SubElement(rel, 'checksum')
                csum.text = md.fw.checksum_signed
                csum.set('type', 'sha1')
                csum.set('filename', md.fw.filename)
                csum.set('target', 'container')

            # add content checksum
            if md.checksum_contents:
                csum = ET.SubElement(rel, 'checksum')
                csum.text = md.checksum_contents
                csum.set('type', 'sha1')
                csum.set('filename', md.filename_contents)
                csum.set('target', 'content')

            # add long description
            if md.release_description:
                rel.append(_xml_from_markdown(md.release_description))

            # add sizes if set
            if md.release_installed_size:
                sz = ET.SubElement(rel, 'size')
                sz.set('type', 'installed')
                sz.text = str(md.release_installed_size)
            if md.release_download_size:
                sz = ET.SubElement(rel, 'size')
                sz.set('type', 'download')
                sz.text = str(md.release_download_size)

        # provides shared by all releases
        elements = {}
        for md in mds:
            for guid in md.guids:
                if guid.value in elements:
                    continue
                child = ET.Element('firmware')
                child.set('type', 'flashed')
                child.text = guid.value
                elements[guid.value] = child
        if elements:
            parent = ET.SubElement(component, 'provides')
            for key in sorted(elements):
                parent.append(elements[key])

        # metadata shared by all releases
        elements = {}
        for md in mds:
            if md.inhibit_download:
                if 'LVFS::InhibitDownload' in elements:
                    continue
                child = ET.Element('value')
                child.set('key', 'LVFS::InhibitDownload')
                elements['LVFS::InhibitDownload'] = child
            if md.version_format:
                if 'LVFS::VersionFormat' in elements:
                    continue
                child = ET.Element('value')
                child.set('key', 'LVFS::VersionFormat')
                child.text = md.version_format
                elements['LVFS::VersionFormat'] = child
        if elements:
            parent = ET.SubElement(component, 'metadata')
            for key in elements:
                parent.append(elements[key])

    # dump to file
    et = ET.ElementTree(root)
    et.write(filename,
             encoding='utf-8',
             xml_declaration=True,
             compression=5,
             pretty_print=True)

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

        # all firmwares are contained in the correct metadata now
        for fw in fws_filtered:
            fw.is_dirty = False

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
