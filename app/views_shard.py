#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2019 Richard Hughes <richard@hughsie.com>
#
# SPDX-License-Identifier: GPL-2.0+

from flask import request, url_for, redirect, flash, render_template
from flask_login import login_required

from app import app, db

from .models import ComponentShardInfo
from .util import admin_login_required

@app.route('/lvfs/shard/all')
@login_required
@admin_login_required
def shard_all():

    # only show shards with the correct group_id
    shards = db.session.query(ComponentShardInfo).order_by(ComponentShardInfo.cnt.desc()).all()
    return render_template('shard-list.html',
                           category='admin',
                           shards=shards)

@app.route('/lvfs/shard/<int:component_shard_info_id>/modify', methods=['POST'])
@login_required
@admin_login_required
def shard_modify(component_shard_info_id):

    # find shard
    shard = db.session.query(ComponentShardInfo).\
                filter(ComponentShardInfo.component_shard_info_id == component_shard_info_id).first()
    if not shard:
        flash('No shard found', 'info')
        return redirect(url_for('.shard_all'))

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
@admin_login_required
def shard_details(component_shard_info_id):

    # find shard
    shard = db.session.query(ComponentShardInfo).\
            filter(ComponentShardInfo.component_shard_info_id == component_shard_info_id).first()
    if not shard:
        flash('No shard found', 'info')
        return redirect(url_for('.shard_all'))

    # show details
    return render_template('shard-details.html',
                           category='admin',
                           shard=shard)
