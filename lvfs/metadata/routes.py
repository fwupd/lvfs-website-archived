#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2017-2018 Richard Hughes <richard@hughsie.com>
#
# SPDX-License-Identifier: GPL-2.0+

import humanize

from flask import Blueprint, render_template, make_response, flash, redirect, url_for
from flask_login import login_required

from lvfs import db, celery

from lvfs.models import Vendor, Remote
from lvfs.util import admin_login_required

from .utils import _async_regenerate_remote_all, _async_regenerate_remote

bp_metadata = Blueprint('metadata', __name__, template_folder='templates')

@celery.on_after_finalize.connect
def setup_periodic_tasks(sender, **_):
    sender.add_periodic_task(14400.0, _async_regenerate_remote_all.s(), options={'queue': 'metadata'})

@bp_metadata.route('/<group_id>')
@login_required
def route_remote(group_id):
    """
    Generate a remote file for a given QA group.
    """

    # find the vendor
    vendor = db.session.query(Vendor).filter(Vendor.group_id == group_id).first()
    if not vendor:
        flash('No vendor with that name', 'danger')
        return redirect(url_for('metadata.route_view'))

    # security check
    if not vendor.check_acl('@view-metadata'):
        flash('Permission denied: Unable to view metadata', 'danger')
        return redirect(url_for('metadata.route_view'))

    # generate file
    remote = []
    remote.append('[fwupd Remote]')
    remote.append('Enabled=true')
    remote.append('Title=Embargoed for ' + group_id)
    remote.append('Keyring=gpg')
    remote.append('MetadataURI=https://fwupd.org/downloads/%s' % vendor.remote.filename_newest)
    remote.append('ReportURI=https://fwupd.org/lvfs/firmware/report')
    remote.append('OrderBefore=lvfs,fwupd')
    fn = group_id + '-embargo.conf'
    response = make_response('\n'.join(remote))
    response.headers['Content-Disposition'] = 'attachment; filename=' + fn
    response.mimetype = 'text/plain'
    return response

@bp_metadata.route('/')
@login_required
def route_view():
    """
    Show all metadata available to this user.
    """

    # show all embargo metadata URLs when admin user
    vendors = []
    for vendor in db.session.query(Vendor):
        if vendor.is_account_holder and vendor.check_acl('@view-metadata'):
            vendors.append(vendor)
    remotes = {}
    for r in db.session.query(Remote):
        remotes[r.name] = r
    return render_template('metadata.html',
                           category='firmware',
                           vendors=vendors,
                           remotes=remotes)

@bp_metadata.route('/rebuild', methods=['POST'])
@login_required
@admin_login_required
def route_rebuild():
    """
    Forces a rebuild of all metadata.
    """

    # update metadata
    scheduled_signing = None
    for r in db.session.query(Remote).filter(Remote.is_public):
        r.is_dirty = True
        if not scheduled_signing:
            scheduled_signing = r.scheduled_signing
    for vendor in db.session.query(Vendor):
        if vendor.is_account_holder:
            vendor.remote.is_dirty = True
    if scheduled_signing:
        flash('Metadata will be rebuilt %s' % humanize.naturaltime(scheduled_signing), 'info')
    return redirect(url_for('metadata.route_view'))

@bp_metadata.route('/rebuild/<remote_id>', methods=['POST'])
@login_required
@admin_login_required
def route_rebuild_remote(remote_id):
    """
    Forces a rebuild of one metadata remote.
    """

    # update metadata
    r = db.session.query(Remote).filter(Remote.remote_id == remote_id).first()
    if not r:
        flash('No remote with that ID', 'danger')
        return redirect(url_for('metadata.route_view'))
    r.is_dirty = True
    db.session.commit()

    # asynchronously rebuilt
    flash('Remote {} is being regenerated'.format(r.name), 'info')
    _async_regenerate_remote.apply_async(args=(r.remote_id,), queue='metadata')

    return redirect(url_for('metadata.route_view'))
