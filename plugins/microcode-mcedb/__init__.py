#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2020 Richard Hughes <richard@hughsie.com>
#
# SPDX-License-Identifier: GPL-2.0+
#
# pylint: disable=no-self-use

import os
import sqlite3
import datetime

from lvfs import db
from lvfs.pluginloader import PluginBase, PluginSettingBool, PluginSettingText
from lvfs.models import Test, Claim
from lvfs.models import _get_datestr_from_datetime
from lvfs.util import _get_shard_path

class Plugin(PluginBase):
    def __init__(self):
        PluginBase.__init__(self)
        self.name = 'Microcode MCEdb'
        self.summary = 'Check the microcode is not older than latest release'
        self.order_after = ['uefi-extract']

    def settings(self):
        s = []
        s.append(PluginSettingBool('microcode_mcedb_enabled', 'Enabled', False))
        s.append(PluginSettingText('microcode_mcedb_path', 'Path to MCE.db', 'MCExtractor/MCE.db'))
        return s

    def require_test_for_md(self, md):

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

        # load database
        mcefn = self.get_setting('microcode_mcedb_path', required=True)
        if not os.path.exists(mcefn):
            test.add_fail('cannot locate database: {}'.format(mcefn))
            return
        conn = sqlite3.connect(mcefn)
        c = conn.cursor()
        c.execute('SELECT version, yyyymmdd FROM Intel WHERE cpuid=? AND '
                  'platform=? AND version>? AND yyyymmdd>? ORDER BY version LIMIT 1',
                  (cpuid, platform, version, datestr_upload))
        res = c.fetchone()
        if res:
            (newest_version, newset_datestr,) = res
            print('CPUID:{:#x} Platform:{:#x} version {:#x} (released on {}) may be older '
                  'than latest released version {:#x} (released on {})'.\
                  format(int(cpuid, 16),
                         int(platform, 16),
                         int(version, 16),
                         datestr,
                         int(newest_version, 16),
                         newset_datestr))
            claim = db.session.query(Claim)\
                              .filter(Claim.kind == 'old-microcode')\
                              .first()
            if claim:
                shard.md.add_claim(claim)
        else:
            c.execute('SELECT version FROM Intel WHERE cpuid=? AND '
                      'platform=? AND version==? LIMIT 1',
                      (cpuid, platform, version,))
            if not c.fetchone():
                print('microcode NOT FOUND, please upload: {}'.format(_get_shard_path(shard)))
        c.close()

    def run_test_on_md(self, test, md):
        for shard in md.shards:
            self._run_test_on_shard(test, shard)
