#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2019-2020 Richard Hughes <richard@hughsie.com>
#
# SPDX-License-Identifier: GPL-2.0+
#
# pylint: disable=no-self-use,no-member,too-few-public-methods,unused-argument,singleton-comparison

from lvfs import db
from lvfs.pluginloader import PluginBase
from lvfs.models import Test, ComponentShard, ComponentShardInfo, \
                        ComponentShardClaim, ComponentShardChecksum, Claim

class Plugin(PluginBase):
    def __init__(self, plugin_id=None):
        PluginBase.__init__(self, plugin_id)
        self.infos_by_guid = {}
        self.claims_by_csum = {}
        self.name = 'Shard Claim'
        self.summary = 'Add component claims based on shard GUIDs'
        self.order_after = ['uefi-extract']

    def ensure_test_for_fw(self, fw):

        # add if not already exists
        test = fw.find_test_by_plugin_id(self.id)
        if not test:
            test = Test(self.id, waivable=True)
            fw.tests.append(test)

    def run_test_on_fw(self, test, fw):

        # find any infos that indicate a claim
        if not self.infos_by_guid:
            for info in db.session.query(ComponentShardInfo)\
                                  .filter(ComponentShardInfo.claim_id != None):
                self.infos_by_guid[info.guid] = info
        if not self.claims_by_csum:
            for claim in db.session.query(ComponentShardClaim)\
                                   .filter(ComponentShardClaim.checksum != None):
                self.claims_by_csum[claim.checksum] = claim

        # get cache of all known claims
        claims = {}
        for claim in db.session.query(Claim).all():
            claims[claim.kind] = claim

    def run_test_on_md(self, test, md):

        # run analysis on the component and any shards
        for shard in md.shards:
            if shard.guid in self.infos_by_guid:
                info = self.infos_by_guid[shard.guid]
                md.add_claim(info.claim)
            if shard.checksum in self.claims_by_csum:
                shard_claim = self.claims_by_csum[shard.checksum]
                md.add_claim(shard_claim.claim)

# run with PYTHONPATH=. ./env/bin/python3 plugins/shard-claim/__init__.py
if __name__ == '__main__':
    import sys
    from lvfs.models import Firmware, Component

    plugin = Plugin('shard-claim')
    _test = Test(plugin.id)
    _fw = Firmware()
    _md = Component()
    _shard = ComponentShard(guid='f114faa8-4fd5-4b95-8bc3-bc5cb5454966')
    _shard.checksums.append(ComponentShardChecksum(kind='SHA256',
                                                   value='fd14d82dd6f4f6fdc3263c25c681b11ef8'\
                                                         'daccd169efcab451cbb32c5f45ef8a'))
    _md.shards.append(_shard)
    _fw.mds.append(_md)
    plugin.run_test_on_fw(_test, _fw)
    plugin.run_test_on_md(_test, _md)
    for _claim in _md.claims:
        print(_claim)
