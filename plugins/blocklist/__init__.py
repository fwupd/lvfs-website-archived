#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2019 Richard Hughes <richard@hughsie.com>
# Licensed under the GNU General Public License Version 2
#
# pylint: disable=no-self-use,no-member,too-few-public-methods

import os

from app import db
from app.pluginloader import PluginBase, PluginError
from app.pluginloader import PluginSettingBool, PluginSettingTextList
from app.models import Test

def _run_on_blob(self, test, title, blob):

    # find in a few different encodings
    values = self.get_setting('blocklist_values', required=True).split(',')
    for value in values:
        try:
            match, desc = value.rsplit('::', 2)
        except ValueError:
            desc = None
            match = value
        for encoding in ['utf8', 'utf_16_le', 'utf_16_be']:
            offset = blob.find(match.encode(encoding))
            if offset != -1:
                if desc:
                    test.add_fail(title, 'Found: {}: {}'.format(match, desc))
                else:
                    test.add_fail(title, 'Found: {}'.format(match))

    return len(values)

class Plugin(PluginBase):
    def __init__(self, plugin_id=None):
        PluginBase.__init__(self, plugin_id)

    def name(self):
        return 'Blocklist'

    def summary(self):
        return 'Use a simple blocklist to check firmware for problems'

    def order_after(self):
        return ['chipsec', 'intelme']

    def settings(self):
        s = []
        s.append(PluginSettingBool('blocklist_enabled', 'Enabled', True))
        s.append(PluginSettingTextList('blocklist_values', 'Values',
                                       ['DO NOT TRUST::IBV example certificate being used',
                                        'DO NOT SHIP::IBV example certificate being used']))
        return s

    def ensure_test_for_fw(self, fw):

        # add if not already exists
        test = fw.find_test_by_plugin_id(self.id)
        if not test:
            test = Test(self.id, waivable=True)
            fw.tests.append(test)

    def run_test_on_fw(self, test, fw):

        # run analysis on the component and any shards
        cnt = 0
        for md in fw.mds:
            if md.blob:
                cnt += _run_on_blob(self, test, md.filename_contents, md.blob)
            for shard in md.shards:
                if shard.blob:
                    cnt += _run_on_blob(self, test, shard.info.name, shard.blob)
        if not cnt:
            test.add_pass('No blobs to scan')
            return

# run with PYTHONPATH=. ./.env3/bin/python3 plugins/blocklist/__init__.py
if __name__ == '__main__':
    import sys
    from app.models import Firmware, Component

    plugin = Plugin('blocklist')
    _test = Test(plugin.id)
    _fw = Firmware()
    _md = Component()
    _md.blob = b'CN=DO NOT TRUST - AMI Test PK'
    _fw.mds.append(_md)
    plugin.run_test_on_fw(_test, _fw)
    for attribute in _test.attributes:
        print(attribute)
