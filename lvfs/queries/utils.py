#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2017-2018 Richard Hughes <richard@hughsie.com>
#
# SPDX-License-Identifier: GPL-2.0+
#
# pylint: disable=singleton-comparison

import datetime

import yara

from lvfs import db

from lvfs.models import Remote, Firmware, Component, YaraQuery, YaraQueryResult

def _query_run_shard(query, md, shard):
    if not shard.blob:
        return
    matches = query.rules.match(data=shard.blob)
    for match in matches:
        msg = match.rule
        for string in match.strings:
            if len(string) == 3:
                try:
                    msg += ': found {}'.format(string[2].decode())
                except UnicodeDecodeError as _:
                    pass
        query.results.append(YaraQueryResult(md=md, shard=shard, result=msg))

    # unallocate the cached blob as it's no longer needed
    shard.blob = None

def _query_run_component(query, md):
    if not md.blob:
        return
    matches = query.rules.match(data=md.blob)
    for match in matches:
        msg = match.rule
        for string in match.strings:
            if len(string) == 3:
                try:
                    msg += ': found {}'.format(string[2].decode())
                except UnicodeDecodeError as _:
                    pass
        query.results.append(YaraQueryResult(md=md, result=msg))

    # unallocate the cached blob as it's no longer needed
    md.blob = None

def _query_run(query):
    print('processing query {}: {}...'.format(query.yara_query_id, query.title))
    try:
        query.rules = yara.compile(source=query.value)
    except yara.SyntaxError as e:
        query.error = 'Failed to compile rules: {}'.format(str(e))
        db.session.commit()
        return
    query.started_ts = datetime.datetime.utcnow()
    db.session.commit()
    component_ids = [x[0] for x in db.session.query(Component.component_id)\
                                             .join(Firmware)\
                                             .join(Remote)\
                                             .filter(Remote.name == 'stable').all()]
    for component_id in component_ids:
        md = db.session.query(Component)\
                       .filter(Component.component_id == component_id)\
                       .one()
        for shard in md.shards:
            _query_run_shard(query, md, shard)
        _query_run_component(query, md)
        query.total += len(md.shards)
    query.found = len(query.results)
    query.ended_ts = datetime.datetime.utcnow()
    db.session.commit()

def _query_run_all():

    # get all pending queries
    pending = db.session.query(YaraQuery).\
                    filter(YaraQuery.started_ts == None).\
                    filter(YaraQuery.error == None)
    for query in pending:
        _query_run(query)
