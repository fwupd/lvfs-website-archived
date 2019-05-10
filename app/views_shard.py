#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2019 Richard Hughes <richard@hughsie.com>
# Licensed under the GNU General Public License Version 2

from flask import request, url_for, redirect, flash, g, render_template
from flask_login import login_required

from app import app, db

from .models import ComponentShardInfo
from .util import _error_permission_denied

@app.route('/lvfs/shard/all')
@login_required
def shard_all():

    # security check
    if not g.user.check_acl('@view-shards'):
        return _error_permission_denied('Unable to view shards')

    # only show shards with the correct group_id
    shards = db.session.query(ComponentShardInfo).order_by(ComponentShardInfo.cnt.desc()).all()
    return render_template('shard-list.html',
                           category='admin',
                           shards=shards)

@app.route('/lvfs/shard/<int:component_shard_info_id>/modify', methods=['POST'])
@login_required
def shard_modify(component_shard_info_id):

    # find shard
    shard = db.session.query(ComponentShardInfo).\
                filter(ComponentShardInfo.component_shard_info_id == component_shard_info_id).first()
    if not shard:
        flash('No shard found', 'info')
        return redirect(url_for('.shard_all'))

    # security check
    if not shard.check_acl('@modify'):
        return _error_permission_denied('Unable to modify shard')

    # modify shard
    for key in ['name', 'description']:
        if key in request.form:
            setattr(shard, key, request.form[key])
    db.session.commit()

    # success
    flash('Modified shard', 'info')
    return shard_details(component_shard_info_id)

@app.route('/lvfs/shard/<int:component_shard_info_id>/details')
@login_required
def shard_details(component_shard_info_id):

    # find shard
    shard = db.session.query(ComponentShardInfo).\
            filter(ComponentShardInfo.component_shard_info_id == component_shard_info_id).first()
    if not shard:
        flash('No shard found', 'info')
        return redirect(url_for('.shard_all'))

    # security check
    if not shard.check_acl('@view'):
        return _error_permission_denied('Unable to view shard details')

    # show details
    return render_template('shard-details.html',
                           category='admin',
                           shard=shard)
