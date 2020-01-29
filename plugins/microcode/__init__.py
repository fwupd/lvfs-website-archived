#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2020 Richard Hughes <richard@hughsie.com>
#
# SPDX-License-Identifier: GPL-2.0+
#
# pylint: disable=no-self-use

import datetime

from lvfs.pluginloader import PluginBase, PluginSettingBool
from lvfs.models import Test, ComponentShard, ComponentShardAttribute
from lvfs.models import _get_datestr_from_datetime
from lvfs import db

class Plugin(PluginBase):
    def __init__(self):
        PluginBase.__init__(self)
        self.name = 'Microcode Version'
        self.summary = 'Check the microcode is not downgraded'
        self.order_after = ['uefi-extract']

    def settings(self):
        s = []
        s.append(PluginSettingBool('microcode_enabled', 'Enabled', True))
        return s

    def require_test_for_md(self, md):

        # not for firmware already in stable
        if md.fw.remote.is_public:
            return False

        # only run for capsule updates
        if not md.protocol:
            return False
        if not md.blob:
            return False
        return md.protocol.value == 'org.uefi.capsule'

    def ensure_test_for_fw(self, fw):

        # if not already exists
        test = fw.find_test_by_plugin_id(self.id)
        if not test:
            test = Test(plugin_id=self.id, waivable=True)
            fw.tests.append(test)

    def _run_test_on_shard(self, test, shard):

        # only Intel μcode supported at this time
        if shard.guid != '3f0229ad-0a00-5269-90cf-0a45d8781b72':
            return

        # get required attributes
        cpuid = shard.get_attr_value('cpuid')
        if not cpuid:
            return
        platform = shard.get_attr_value('platform')
        if not platform:
            return
        version = shard.get_attr_value('version')
        if not version:
            return
        datestr = shard.get_attr_value('yyyymmdd')
        if not datestr:
            return

        # don't expect vendors to include microcode that was released *after*
        # the file was uploaded to the LVFS
        datestr_upload = str(_get_datestr_from_datetime(shard.md.fw.timestamp))

        # find any higher microcode version larger than this one known to the LVFS
        stmt1 = db.session.query(ComponentShard.component_shard_id)\
                          .join(ComponentShardAttribute)\
                          .filter(ComponentShardAttribute.key == 'cpuid')\
                          .filter(ComponentShardAttribute.value == cpuid)\
                          .subquery()
        stmt2 = db.session.query(ComponentShard.component_shard_id)\
                          .join(ComponentShardAttribute)\
                          .filter(ComponentShardAttribute.key == 'platform')\
                          .filter(ComponentShardAttribute.value == platform)\
                          .subquery()
        stmt3 = db.session.query(ComponentShard.component_shard_id)\
                          .join(ComponentShardAttribute)\
                          .filter(ComponentShardAttribute.key == 'yyyymmdd')\
                          .filter(ComponentShardAttribute.value < datestr_upload)\
                          .subquery()
        shards = db.session.query(ComponentShard)\
                           .join(stmt1, ComponentShard.component_shard_id == stmt1.c.component_shard_id)\
                           .join(stmt2, ComponentShard.component_shard_id == stmt2.c.component_shard_id)\
                           .join(stmt3, ComponentShard.component_shard_id == stmt3.c.component_shard_id)\
                           .join(ComponentShardAttribute)\
                           .filter(ComponentShardAttribute.key == 'version')\
                           .filter(ComponentShardAttribute.value > version)\
                           .order_by(ComponentShardAttribute.value)\
                           .all()
        for shard_tmp in shards:
            if shard_tmp.md.fw.remote.is_public:

                # an update can be created for resolving vendor-specific or
                # model-specific issues, so restrict results to the AppStream ID
                if shard.md.appstream_id != shard_tmp.md.appstream_id:
                    continue

                # only count firmware older than the correct firmware
                if shard.md < shard_tmp.md:
                    continue

                newest_version = shard_tmp.get_attr_value('version')
                newset_datestr = shard_tmp.get_attr_value('yyyymmdd')
                test.add_fail('Downgraded Intel CPU microcode detected',
                              'CPUID:{:#x} Platform:{:#x} version {:#x} (released on {}) is older '
                              'than latest released version {:#x} (released on {}) found in {} v{}'\
                              .format(int(cpuid, 16),
                                      int(platform, 16),
                                      int(version, 16),
                                      datestr,
                                      int(newest_version, 16),
                                      newset_datestr,
                                      shard_tmp.md.name_with_category,
                                      shard_tmp.md.version_display))
                return

    def run_test_on_md(self, test, md):
        for shard in md.shards:
            self._run_test_on_shard(test, shard)
