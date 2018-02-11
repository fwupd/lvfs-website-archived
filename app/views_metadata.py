#!/usr/bin/python2
# -*- coding: utf-8 -*-
#
# Copyright (C) 2017-2018 Richard Hughes <richard@hughsie.com>
# Licensed under the GNU General Public License Version 2

from flask import render_template, g, make_response, flash, redirect, url_for
from flask_login import login_required

from app import app, db

from .hash import _qa_hash
from .metadata import _metadata_update_group, _metadata_update_targets, _metadata_update_pulp
from .models import UserCapability, Group
from .util import _error_internal, _error_permission_denied

@login_required
@app.route('/lvfs/metadata/<qa_group>')
def metadata_remote(qa_group):
    """
    Generate a remote file for a given QA group.
    """

    # find the Group
    if not db.session.query(Group).filter(Group.group_id == qa_group).first():
        return _error_internal('No QA Group')

    # generate file
    remote = []
    remote.append('[fwupd Remote]')
    remote.append('Enabled=true')
    remote.append('Title=Embargoed for ' + qa_group)
    remote.append('Keyring=gpg')
    remote.append('MetadataURI=https://fwupd.org/downloads/firmware-' + _qa_hash(qa_group) + '.xml.gz')
    remote.append('OrderBefore=lvfs,fwupd')
    fn = qa_group + '-embargo.conf'
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
    group_ids = []
    if g.user.check_capability(UserCapability.Admin):
        for group in db.session.query(Group).all():
            group_ids.append(group.group_id)
    else:
        group_ids.append(g.user.group_id)
    return render_template('metadata.html',
                           group_id=g.user.group_id,
                           group_ids=group_ids)

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
    for group in db.session.query(Group).all():
        _metadata_update_group(group.group_id)
    _metadata_update_targets(['stable', 'testing'])
    _metadata_update_pulp()
    flash('Metadata rebuilt successfully', 'info')
    return redirect(url_for('.metadata_view'))
