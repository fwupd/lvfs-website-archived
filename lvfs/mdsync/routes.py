#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2019 Richard Hughes <richard@hughsie.com>
#
# SPDX-License-Identifier: GPL-2.0+

import json
import gzip

from collections import defaultdict
import dateutil.parser

from flask import Blueprint, request, url_for, redirect, flash, Response, render_template, g
from flask_login import login_required

from lvfs import db, csrf

from lvfs.models import Firmware, Component, Remote, ComponentRef, Protocol, Vendor
from lvfs.util import _json_success, _json_error

bp_mdsync = Blueprint('mdsync', __name__, template_folder='templates')

def _md_to_mdsync_dict(md):
    obj = {}
    obj['component_id'] = md.component_id
    obj['status'] = md.fw.remote.icon_name
    if md.fw.remote.is_public:
        if md.fw.signed_timestamp:
            obj['date'] = md.fw.signed_timestamp.isoformat()
        if md.release_tag:
            obj['release_tag'] = md.release_tag
        if md.details_url:
            obj['changelog_url'] = md.details_url
        if md.fw.success:
            obj['success'] = md.fw.success
            obj['success_confidence'] = md.fw.success_confidence
    return obj

def _mds_to_mdsync_dict(mds):
    obj = {}
    for md in sorted(mds):
        if not md.fw.vendor.visible:
            continue
        obj[md.version_display] = _md_to_mdsync_dict(md)
    return obj

def _any_public(mds):
    for md in mds:
        if md.fw.remote.is_public:
            return True
    return False

@bp_mdsync.route('/export')
@csrf.exempt
@login_required
def route_export():

    # security check
    if not g.user.check_acl('@partner'):
        return _json_error('Permission denied: Unable to export data')

    # get a dict of all stable components, with the appstream-id as dedupe-key
    mds_by_ids = defaultdict(list)
    for md in db.session.query(Component).\
                    join(Firmware).\
                    join(Remote).\
                    filter(Remote.name != 'private',
                           Remote.name != 'deleted').\
                    order_by(Component.appstream_id):
        mds_by_ids[md.appstream_id].append(md)

    # export the devices
    obj_devs = []
    for mds_by_id in mds_by_ids:
        obj_dev = {}

        # don't include devices that have not had a single public release
        mds = mds_by_ids[mds_by_id]
        if not _any_public(mds):
            continue

        # assume these are all the same
        md_first = mds[0]
        obj_dev['appstream_id'] = md_first.appstream_id
        obj_dev['names'] = md_first.names
        obj_dev['vendor_id'] = md_first.fw.vendor.vendor_id
        if md_first.protocol:
            obj_dev['protocol'] = md_first.protocol.value

        # add different versions
        obj_dev['versions'] = _mds_to_mdsync_dict(mds_by_ids[mds_by_id])
        obj_devs.append(obj_dev)
    blob = {}
    blob['metadata'] = {'version': 0}
    blob['devices'] = obj_devs
    dat = json.dumps(blob, indent=4, separators=(',', ': '))
    return Response(response=dat,
                    status=400, \
                    mimetype="application/json")

def _get_plausible_versions_for_md(md):
    versions = [md.version_display]
    if md.version not in versions:
        versions.append(md.version)
    if md.version_display.startswith('0.'):
        versions.append(md.version_display[2:])
    return versions

@bp_mdsync.route('/import', methods=['POST'])
@csrf.exempt
@login_required
def route_import():

    # security check
    if not g.user.check_acl('@partner'):
        return _json_error('Permission denied: Unable to import data')

    # manual upload
    if 'file' in request.files:
        request_data = request.files['file'].read()
    else:
        request_data = request.data

    # parse JSON data, which can be optionally compressed
    try:
        payload = gzip.decompress(request_data)
    except OSError as e:
        payload = request_data.decode('utf8')
    try:
        obj = json.loads(payload)
    except ValueError as e:
        return _json_error('No JSON object could be decoded: ' + str(e))

    # get available protocols
    protocols = {}
    for protocol in db.session.query(Protocol):
        protocols[protocol.value] = protocol

    # get available components
    mds_by_id = {}
    mds_by_tag = {}
    mds_by_ver = {}
    for md in db.session.query(Component).\
                            join(Firmware).\
                            join(Remote).\
                            filter(Remote.name != 'private',
                                   Remote.name != 'deleted'):
        mds_by_id[md.component_id] = md
        for version in _get_plausible_versions_for_md(md):
            mds_by_ver['{}/{}'.format(md.appstream_id, version)] = md
        if md.release_tag:
            mds_by_tag['{}/{}'.format(md.appstream_id, md.release_tag.casefold())] = md

    # get available vendors
    vendors = {}
    for vendor in db.session.query(Vendor).filter(Vendor.visible):
        vendors[vendor.vendor_id] = vendor

    # delete all old mdrefs from this vendor, and force a commit
    for mdref in db.session.query(ComponentRef).\
                    filter(ComponentRef.vendor_id_partner == g.user.vendor_id):
        db.session.delete(mdref)
    db.session.commit()

    # parse blob
    if 'metadata' not in obj:
        return _json_error('metadata object missing')
    metadata = obj['metadata']
    if metadata['version'] != 0:
        return _json_error('metadata schema version unsupported: ' + str(e))
    if 'devices' not in obj:
        return _json_error('devices object missing')
    for obj_dev in obj['devices']:
        try:
            # may be missing for devices not (yet) in LVFS
            appstream_id = obj_dev.get('appstream_id', None)

            # has to match something specified on the LVFS if specified
            if 'protocol' in obj_dev:
                protocol = protocols.get(obj_dev['protocol'], None)
            else:
                protocol = None

            # squash this together as one string as it's only used for analysis
            name = '/'.join(obj_dev.get('names', []))

            # parse each version for the model
            for version in obj_dev['versions']:
                obj_ver = obj_dev['versions'][version]

                # the component_id is optional, but allows the LVFS to link FW
                md = None
                if 'component_id' in obj_ver:
                    md = mds_by_id.get(obj_ver['component_id'], None)

                # release_tag uniquely identifies the firmware download
                release_tag = obj_ver.get('release_tag', None)
                if release_tag and release_tag.find('_') != -1:
                    # this will be fixed by the importer...
                    release_tag = None

                # date has to be in ISO8601 format
                date = None
                if 'date' in obj_ver:
                    try:
                        date = dateutil.parser.parse(obj_ver['date'])
                    except dateutil.parser.ParserError as _:
                        pass

                # prefer the changelog url
                url = obj_ver.get('changelog_url', None)
                if not url:
                    url = obj_ver.get('file_url', None)

                # try getting the md using the appstream-id and the version/tag
                if appstream_id:
                    if not md:
                        md = mds_by_ver.get('{}/{}'.format(appstream_id, version), None)
                    if not md and release_tag:
                        md = mds_by_tag.get('{}/{}'.format(appstream_id, release_tag.casefold()), None)

                # prefer the vendor from the component but fallback to the vendor ID
                vendor = None
                if md:
                    vendor = md.fw.vendor
                elif 'vendor_id' in obj_dev:
                    vendor = vendors.get(int(obj_dev['vendor_id']), None)
                if not vendor:
                    continue

                # add to database
                mdref = ComponentRef(appstream_id=appstream_id,
                                     version=version,
                                     date=date,
                                     md=md,
                                     status=obj_ver.get('status', None),
                                     release_tag=release_tag,
                                     url=url,
                                     name=name,
                                     vendor=vendor,
                                     vendor_partner=g.user.vendor,
                                     protocol=protocol)
                db.session.add(mdref)
        except KeyError as e:
            return _json_error('JSON {} invalid: {}'.format(obj_dev, str(e)))

    # commit new mdrefs
    db.session.commit()

    return _json_success()

@bp_mdsync.route('/')
@login_required
def route_list():

    # security check
    if not g.user.check_acl('@vendor-manager'):
        return redirect(url_for('main.route_dashboard'), 302)

    # we're just showing public vendors on the LVFS
    # and firmware scraped from other public sources
    if g.user.check_acl('@admin'):
        stmt = db.session.query(ComponentRef.vendor_id_partner).\
                                distinct().subquery()
        vendors = db.session.query(Vendor).\
                                   join(stmt, Vendor.vendor_id == stmt.c.vendor_id_partner).\
                                   all()
    else:
        stmt = db.session.query(ComponentRef.vendor_id_partner).\
                                distinct().subquery()
        vendors = db.session.query(Vendor).\
                                   filter(Vendor.visible).\
                                   join(stmt, Vendor.vendor_id == stmt.c.vendor_id_partner).\
                                   all()
    return render_template('mdsync-list.html',
                           category='telemetry',
                           vendors=vendors)

@bp_mdsync.route('/<int:vendor_id_partner>/<int:vendor_id>')
@login_required
def route_show(vendor_id_partner, vendor_id):

    # security check
    if not g.user.check_acl('@vendor-manager') and not g.user.check_acl('@partner'):
        return redirect(url_for('main.route_dashboard'), 302)
    vendor_partner = db.session.query(Vendor).filter(Vendor.vendor_id == vendor_id_partner).first()
    if not vendor_partner:
        flash('Failed to get vendor details: No vendor partner with that ID', 'warning')
        return redirect(url_for('mdsync.route_list'), 302)
    if not g.user.check_acl('@admin') and not vendor_partner.visible:
        flash('Failed to get vendor details: No visible vendor with that ID', 'warning')
        return redirect(url_for('mdsync.route_list'), 302)
    vendor = db.session.query(Vendor).filter(Vendor.vendor_id == vendor_id).first()
    if not vendor or not vendor.visible:
        flash('Failed to get vendor details: No vendor with that ID', 'warning')
        return redirect(url_for('mdsync.route_list'), 302)
    if not g.user.check_acl('@admin') and not g.user.check_acl('@partner'):
        if vendor.vendor_id != g.user.vendor.vendor_id:
            flash('Failed to get vendor details: Not allowed', 'warning')
            return redirect(url_for('mdsync.route_list'), 302)

    # create filtered list
    mdrefs_by_id = defaultdict(list)
    md_by_id = {}
    mdrefs = db.session.query(ComponentRef).\
                    filter(ComponentRef.vendor_id == vendor_id).\
                    filter(ComponentRef.vendor_id_partner == vendor_id_partner)
    for mdref in mdrefs:
        if mdref.appstream_id:
            mdrefs_by_id[mdref.appstream_id].append(mdref)
        else:
            mdrefs_by_id[mdref.name].append(mdref)
        if mdref.md and mdref.appstream_id:
            md_by_id[mdref.appstream_id] = mdref.md

    return render_template('mdsync-show.html',
                           category='telemetry',
                           vendor=vendor,
                           vendor_partner=vendor_partner,
                           md_by_id=md_by_id,
                           mdrefs_by_id=mdrefs_by_id)

@bp_mdsync.route('/<int:vendor_id_partner>')
@login_required
def route_vendors(vendor_id_partner):

    # security check
    if not g.user.check_acl('@vendor-manager') and not g.user.check_acl('@partner'):
        return redirect(url_for('main.route_dashboard'), 302)

    # another security check
    vendor_partner = db.session.query(Vendor).filter(Vendor.vendor_id == vendor_id_partner).first()
    if not vendor_partner:
        flash('Failed to get vendor details: No vendor partner with that ID', 'warning')
        return redirect(url_for('mdsync.route_list'), 302)
    if not g.user.check_acl('@admin') and not vendor_partner.visible:
        flash('Failed to get vendor details: No visible vendor with that ID', 'warning')
        return redirect(url_for('mdsync.route_list'), 302)

    # non partner accounts can only see one vendor anyway, so redirect
    if not g.user.check_acl('@admin') and not g.user.check_acl('@partner'):
        return redirect(url_for('mdsync.route_show',
                                vendor_id_partner=vendor_id_partner,
                                vendor_id=g.user.vendor_id))

    # get all the different OEMs we have data on from this partner
    stmt = db.session.query(ComponentRef.vendor_id).\
                            filter(ComponentRef.vendor_id_partner == vendor_id_partner).\
                            distinct().subquery()
    vendors = db.session.query(Vendor).\
                               join(stmt, Vendor.vendor_id == stmt.c.vendor_id).\
                               all()
    return render_template('mdsync-vendors.html',
                           category='telemetry',
                           vendor_partner=vendor_partner,
                           vendors=vendors)
