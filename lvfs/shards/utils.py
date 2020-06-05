#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2019-2020 Richard Hughes <richard@hughsie.com>
#
# SPDX-License-Identifier: GPL-2.0+
#
# pylint: disable=singleton-comparison

from lvfs import db, celery

from lvfs.models import ComponentShard, ComponentShardInfo

def _generate_stats_shard_info(info):

    cnt = db.session.query(ComponentShard.component_shard_id)\
                    .filter(ComponentShard.guid == info.guid)\
                    .count()
    if info.cnt != cnt:
        print('fixing ComponentShardInfo %i: %i -> %i' % (info.component_shard_info_id, info.cnt, cnt))
        info.cnt = cnt

def _regenerate_shard_infos():

    # Set ComponentShardInfo in ComponentShard if GUID matches
    infos = {}
    for info in db.session.query(ComponentShardInfo):
        infos[info.guid] = info
    for component_shard_id, in db.session.query(ComponentShard.component_shard_id)\
                                         .filter(ComponentShard.component_shard_info_id == None):
        shard = db.session.query(ComponentShard)\
                          .filter(ComponentShard.component_shard_id == component_shard_id).one()
        shard.info = infos.get(shard.guid)
        if shard.info:
            print('fixing shard {} with {}'.format(component_shard_id, shard.guid))
        else:
            print('creating ComponentShardInfo for {}'.format(shard.guid))
            shard.info = ComponentShardInfo(guid=shard.guid)
            infos[shard.guid] = shard.info
        db.session.commit()

    # update ComponentShardInfo.cnt
    for info_id, in db.session.query(ComponentShardInfo.component_shard_info_id)\
                              .order_by(ComponentShardInfo.component_shard_info_id.asc()):
        info = db.session.query(ComponentShardInfo)\
                         .filter(ComponentShardInfo.component_shard_info_id == info_id)\
                         .one()
        _generate_stats_shard_info(info)
    db.session.commit()

@celery.task(task_time_limit=600)
def _async_regenerate_shard_infos():
    _regenerate_shard_infos()
