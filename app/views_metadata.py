#!/usr/bin/python2
# -*- coding: utf-8 -*-
#
# Copyright (C) 2017-2018 Richard Hughes <richard@hughsie.com>
# Licensed under the GNU General Public License Version 2

from flask import render_template, g, make_response, flash, redirect, url_for
from flask_login import login_required

from app import app, db

from .hash import _qa_hash
from .models import UserCapability, Vendor, Remote
from .util import _error_internal, _error_permission_denied

@login_required
@app.route('/lvfs/metadata/<group_id>')
def metadata_remote(group_id):
    """
    Generate a remote file for a given QA group.
    """

    # find the vendor
    if not db.session.query(Vendor).filter(Vendor.group_id == group_id).first():
        return _error_internal('No vendor with that name')

    # generate file
    remote = []
    remote.append('[fwupd Remote]')
    remote.append('Enabled=true')
    remote.append('Title=Embargoed for ' + group_id)
    remote.append('Keyring=gpg')
    remote.append('MetadataURI=https://fwupd.org/downloads/firmware-' + _qa_hash(group_id) + '.xml.gz')
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
    if g.user.check_capability(UserCapability.Admin):
        for vendor in db.session.query(Vendor).\
                        filter(Vendor.is_account_holder != 'no').all():
            vendors.append(vendor)
    else:
        vendors.append(g.user.vendor)
    remotes = {}
    for r in db.session.query(Remote).all():
        remotes[r.name] = r
    return render_template('metadata.html', vendors=vendors, remotes=remotes)

@app.route('/lvfs/metadata/rebuild')
@login_required
def metadata_rebuild():
    """
    Forces a rebuild of all metadata.
    """

    # security check
    if not g.user.check_capability(UserCapability.Admin):
        return _error_permission_denied('Only admin is allowed to force-rebuild metadata')

    # update metadata
    for r in db.session.query(Remote).filter(Remote.is_public).all():
        r.is_dirty = True
    for vendor in db.session.query(Vendor).\
                    filter(Vendor.is_account_holder != 'no').all():
        vendor.remote.is_dirty = True
    flash('Metadata will be rebuilt soon', 'info')
    return redirect(url_for('.metadata_view'))
