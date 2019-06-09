#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2017-2018 Richard Hughes <richard@hughsie.com>
# Licensed under the GNU General Public License Version 2

import humanize

from flask import render_template, make_response, flash, redirect, url_for
from flask_login import login_required

from app import app, db

from .models import Vendor, Remote
from .util import admin_login_required
from .util import _error_internal, _error_permission_denied

@app.route('/lvfs/metadata/<group_id>')
@login_required
def metadata_remote(group_id):
    """
    Generate a remote file for a given QA group.
    """

    # find the vendor
    vendor = db.session.query(Vendor).filter(Vendor.group_id == group_id).first()
    if not vendor:
        return _error_internal('No vendor with that name')

    # security check
    if not vendor.check_acl('@view-metadata'):
        return _error_permission_denied('Unable to view metadata')

    # generate file
    remote = []
    remote.append('[fwupd Remote]')
    remote.append('Enabled=true')
    remote.append('Title=Embargoed for ' + group_id)
    remote.append('Keyring=gpg')
    remote.append('MetadataURI=https://fwupd.org/downloads/%s' % vendor.remote.filename)
    remote.append('ReportURI=https://fwupd.org/lvfs/firmware/report')
    remote.append('OrderBefore=lvfs,fwupd')
    fn = group_id + '-embargo.conf'
    response = make_response('\n'.join(remote))
    response.headers['Content-Disposition'] = 'attachment; filename=' + fn
    response.mimetype = 'text/plain'
    return response

@app.route('/lvfs/metadata')
@login_required
def metadata_view():
    """
    Show all metadata available to this user.
    """

    # show all embargo metadata URLs when admin user
    vendors = []
    for vendor in db.session.query(Vendor).all():
        if vendor.is_account_holder and vendor.check_acl('@view-metadata'):
            vendors.append(vendor)
    remotes = {}
    for r in db.session.query(Remote).all():
        remotes[r.name] = r
    return render_template('metadata.html',
                           category='firmware',
                           vendors=vendors,
                           remotes=remotes)

@app.route('/lvfs/metadata/rebuild')
@login_required
@admin_login_required
def metadata_rebuild():
    """
    Forces a rebuild of all metadata.
    """

    # update metadata
    scheduled_signing = None
    for r in db.session.query(Remote).filter(Remote.is_public).all():
        r.is_dirty = True
        if not scheduled_signing:
            scheduled_signing = r.scheduled_signing
    for vendor in db.session.query(Vendor).all():
        if vendor.is_account_holder:
            vendor.remote.is_dirty = True
    if scheduled_signing:
        flash('Metadata will be rebuilt %s' % humanize.naturaltime(scheduled_signing), 'info')
    return redirect(url_for('.metadata_view'))

@app.route('/lvfs/metadata/rebuild/<remote_id>')
@login_required
@admin_login_required
def metadata_rebuild_remote(remote_id):
    """
    Forces a rebuild of one metadata remote.
    """

    # update metadata
    r = db.session.query(Remote).filter(Remote.remote_id == remote_id).first()
    if not r:
        return _error_internal('No remote with that ID')
    r.is_dirty = True

    # modify
    db.session.commit()
    flash('Remote %s marked as dirty' % r.name, 'info')
    return redirect(url_for('.metadata_view'))
