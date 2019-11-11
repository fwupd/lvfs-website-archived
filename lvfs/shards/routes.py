#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2019 Richard Hughes <richard@hughsie.com>
#
# SPDX-License-Identifier: GPL-2.0+

from flask import Blueprint, request, url_for, redirect, flash, render_template, make_response
from flask_login import login_required

from lvfs import db

from lvfs.models import ComponentShard, ComponentShardInfo
from lvfs.util import admin_login_required

bp_shards = Blueprint('shards', __name__, template_folder='templates')

@bp_shards.route('/')
@login_required
@admin_login_required
def route_list():

    # only show shards with the correct group_id
    shards = db.session.query(ComponentShardInfo).order_by(ComponentShardInfo.cnt.desc()).all()
    return render_template('shard-list.html',
                           category='admin',
                           shards=shards)

@bp_shards.route('/<int:component_shard_info_id>/modify', methods=['POST'])
@login_required
@admin_login_required
def route_modify(component_shard_info_id):

    # find shard
    shard = db.session.query(ComponentShardInfo).\
                filter(ComponentShardInfo.component_shard_info_id == component_shard_info_id).first()
    if not shard:
        flash('No shard found', 'info')
        return redirect(url_for('shards.route_list'))

    # modify shard
    for key in ['description']:
        if key in request.form:
            setattr(shard, key, request.form[key])
    db.session.commit()

    # success
    flash('Modified shard', 'info')
    return route_show(component_shard_info_id)

@bp_shards.route('/<int:component_shard_info_id>/details')
@login_required
@admin_login_required
def route_show(component_shard_info_id):

    # find shard
    shard = db.session.query(ComponentShardInfo).\
            filter(ComponentShardInfo.component_shard_info_id == component_shard_info_id).first()
    if not shard:
        flash('No shard found', 'info')
        return redirect(url_for('shards.route_list'))

    # show details
    return render_template('shard-details.html',
                           category='admin',
                           shard=shard)

@bp_shards.route('/<int:component_shard_id>/download')
@login_required
@admin_login_required
def route_download(component_shard_id):

    # find shard
    shard = db.session.query(ComponentShard).\
            filter(ComponentShard.component_shard_id == component_shard_id).first()
    if not shard:
        flash('No shard found', 'info')
        return redirect(url_for('shards.route_list'))
    if not shard.md.fw.check_acl('@view'):
        flash('Permission denied: Unable to download shard', 'danger')
        return redirect(url_for('main.route_dashboard'))
    if not shard.blob:
        flash('Permission denied: Shard has no data', 'warning')
        return redirect(url_for('main.route_dashboard'))
    response = make_response(shard.blob)
    response.headers.set('Content-Type', 'application/octet-stream')
    response.headers.set('Content-Disposition', 'attachment', filename=shard.guid)
    return response
