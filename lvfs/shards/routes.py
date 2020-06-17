#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2019 Richard Hughes <richard@hughsie.com>
#
# SPDX-License-Identifier: GPL-2.0+

from collections import defaultdict

from uuid import UUID

from celery.schedules import crontab

from flask import Blueprint, request, url_for, redirect, flash, render_template, make_response
from flask_login import login_required

from lvfs import db, celery

from lvfs.models import ComponentShard, ComponentShardInfo, Component, ComponentShardClaim, Claim
from lvfs.util import admin_login_required

from .utils import _async_regenerate_shard_infos

bp_shards = Blueprint('shards', __name__, template_folder='templates')

@celery.on_after_finalize.connect
def setup_periodic_tasks(sender, **_):
    sender.add_periodic_task(
        crontab(hour=3, minute=0),
        _async_regenerate_shard_infos.s(),
    )

@bp_shards.route('/')
@login_required
@admin_login_required
def route_list():

    # only show shards with the correct group_id
    shards = db.session.query(ComponentShardInfo).order_by(ComponentShardInfo.cnt.desc()).all()
    return render_template('shard-list.html',
                           category='admin',
                           shards=shards)

@bp_shards.route('/create', methods=['POST'])
@login_required
@admin_login_required
def route_create():
    # ensure has enough data
    if 'guid' not in request.form:
        flash('No form data found', 'warning')
        return redirect(url_for('shards.route_list'))
    guid = request.form['guid'].lower()
    try:
        _ = UUID(guid)
    except ValueError:
        flash('Failed to add shard: Not a GUID', 'warning')
        return redirect(url_for('shards.route_list'))

    # already exists
    if db.session.query(ComponentShardInfo).filter(ComponentShardInfo.guid == guid).first():
        flash('Failed to add shard: Already exists', 'info')
        return redirect(url_for('shards.route_list'))

    # add ComponentShardInfo
    shard = ComponentShardInfo(guid=guid)
    db.session.add(shard)
    db.session.commit()
    flash('Added shard', 'info')
    return redirect(url_for('shards.route_show',
                            component_shard_info_id=shard.component_shard_info_id))

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
    for key in ['description', 'claim_id']:
        if key in request.form:
            setattr(shard, key, request.form[key] or None)
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
    claims = db.session.query(Claim).order_by(Claim.summary).all()
    return render_template('shard-details.html',
                           category='admin',
                           claims=claims,
                           shard=shard)

@bp_shards.route('/<int:component_shard_info_id>/components')
@login_required
@admin_login_required
def route_components(component_shard_info_id):

    # find shard
    shard_info = db.session.query(ComponentShardInfo).\
            filter(ComponentShardInfo.component_shard_info_id == component_shard_info_id).first()
    if not shard_info:
        flash('No shard found', 'info')
        return redirect(url_for('shards.route_list'))

    # get shards with a unique component appstream ID
    shards = db.session.query(ComponentShard)\
                       .join(ComponentShardInfo)\
                       .filter(ComponentShardInfo.component_shard_info_id == component_shard_info_id)\
                       .join(Component)\
                       .distinct(Component.appstream_id)\
                       .order_by(Component.appstream_id, ComponentShard.name.desc())\
                       .all()
    unique_mds = defaultdict(list)
    for shard in shards:
        if shard.md not in unique_mds[shard.name]:
            unique_mds[shard.name].append(shard.md)

    # show details
    return render_template('shard-components.html',
                           category='admin',
                           unique_mds=unique_mds,
                           shard=shard_info)

@bp_shards.route('/<int:component_shard_info_id>/checksums')
@login_required
@admin_login_required
def route_checksums(component_shard_info_id):

    # find shard
    shard_info = db.session.query(ComponentShardInfo).\
            filter(ComponentShardInfo.component_shard_info_id == component_shard_info_id).first()
    if not shard_info:
        flash('No shard found', 'info')
        return redirect(url_for('shards.route_list'))

    # get shards with a unique component appstream ID
    shards = db.session.query(ComponentShard)\
                       .join(ComponentShardInfo)\
                       .filter(ComponentShardInfo.component_shard_info_id == component_shard_info_id)\
                       .all()
    unique_mds = defaultdict(list)
    for shard in shards:
        if shard.md not in unique_mds[shard.checksum]:
            unique_mds[shard.checksum].append(shard.md)

    # show details
    return render_template('shard-checksums.html',
                           category='admin',
                           unique_mds=unique_mds,
                           shard=shard_info)

@bp_shards.route('/<int:component_shard_info_id>/claims')
@login_required
@admin_login_required
def route_claims(component_shard_info_id):

    # find shard
    shard = db.session.query(ComponentShardInfo).\
            filter(ComponentShardInfo.component_shard_info_id == component_shard_info_id).first()
    if not shard:
        flash('No shard found', 'info')
        return redirect(url_for('shards.route_list'))

    # get claims for this ComponentShardInfo
    claims = db.session.query(ComponentShardClaim)\
                       .filter(ComponentShardClaim.component_shard_info_id == component_shard_info_id)\
                       .all()

    # show details
    claims_all = db.session.query(Claim).order_by(Claim.summary).all()
    return render_template('shard-claims.html',
                           category='admin',
                           claims=claims,
                           claims_all=claims_all,
                           shard=shard)

@bp_shards.route('/<int:component_shard_info_id>/claim/<int:component_shard_claim_id>/delete', methods=['POST'])
@login_required
@admin_login_required
def route_shard_claim_delete(component_shard_info_id, component_shard_claim_id):

    # find shard
    shard_claim = db.session.query(ComponentShardClaim)\
                            .filter(ComponentShardClaim.component_shard_info_id == component_shard_info_id)\
                            .filter(ComponentShardClaim.component_shard_claim_id == component_shard_claim_id)\
                            .first()
    if not shard_claim:
        flash('No shard claim found', 'info')
        return redirect(url_for('shards.route_list'))
    db.session.delete(shard_claim)
    db.session.commit()
    flash('Deleted shard claim', 'info')
    return redirect(url_for('shards.route_claims',
                            component_shard_info_id=component_shard_info_id))

@bp_shards.route('/<int:component_shard_info_id>/claim/create', methods=['POST'])
@login_required
@admin_login_required
def route_shard_claim_create(component_shard_info_id):

    # ensure has enough data
    for key in ['checksum', 'claim_id']:
        if key not in request.form:
            flash('No {} form data found!'.format(key), 'warning')
            return redirect(url_for('shards.route_list'))

    # already exists
    if db.session.query(ComponentShardClaim)\
                 .filter(ComponentShardClaim.component_shard_info_id == component_shard_info_id)\
                 .filter(ComponentShardClaim.checksum == request.form['checksum'])\
                 .first():
        flash('Failed to add component shard claim: The checksum already exists', 'info')
        return redirect(url_for('issues.route_list'))

    # add issue
    claim = ComponentShardClaim(component_shard_info_id=component_shard_info_id,
                                checksum=request.form['checksum'],
                                claim_id=request.form['claim_id'])
    db.session.add(claim)
    db.session.commit()
    flash('Added claim', 'info')
    return redirect(url_for('shards.route_claims',
                            component_shard_info_id=component_shard_info_id))


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
