#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2019 Richard Hughes <richard@hughsie.com>
#
# SPDX-License-Identifier: GPL-2.0+
#
# pylint: disable=no-self-use,no-member,too-few-public-methods

import os
import glob
import yara

from lvfs import db
from lvfs.pluginloader import PluginBase, PluginError
from lvfs.pluginloader import PluginSettingBool, PluginSettingTextList
from lvfs.models import Test

def _run_on_blob(self, test, md, title, blob):
    matches = self.rules.match(data=blob)
    for match in matches:

        # do what we can
        description = None
        if 'description' in match.meta:
            description = match.meta['description'].replace('\0', '')

        if 'fail' not in match.meta or match.meta['fail']:
            msg = '{} YARA test failed'.format(match.rule)
            for string in match.strings:
                if len(string) == 3:
                    try:
                        msg += ': found {}'.format(string[2].decode())
                    except UnicodeDecodeError as _:
                        pass
            if description:
                msg += ': {}'.format(description)
            test.add_fail(title, msg)
        elif 'claim' in match.meta and description:
            md.add_claim(match.meta['claim'], description)

class Plugin(PluginBase):
    def __init__(self, plugin_id=None):
        PluginBase.__init__(self, plugin_id)
        self.rules = None
        self.name = 'Blocklist'
        self.summary = 'Use YARA to check firmware for problems'

    def order_after(self):
        return ['chipsec', 'intelme']

    def settings(self):
        s = []
        s.append(PluginSettingBool('blocklist_enabled', 'Enabled', True))
        s.append(PluginSettingTextList('blocklist_dirs', 'Rule Directories',
                                       ['plugins/blocklist/rules']))
        return s

    def ensure_test_for_fw(self, fw):

        # add if not already exists
        test = fw.find_test_by_plugin_id(self.id)
        if not test:
            test = Test(self.id, waivable=True)
            fw.tests.append(test)

    def run_test_on_fw(self, test, fw):

        # compile the list of rules
        if not self.rules:
            fns = []
            for value in self.get_setting('blocklist_dirs', required=True).split(','):
                fns.extend(glob.glob(os.path.join(value, '*.yar')))
            if not fns:
                test.add_pass('No YARA rules to use')
                return
            filepaths = {}
            for fn in fns:
                filepaths[os.path.basename(fn)] = fn
            try:
                self.rules = yara.compile(filepaths=filepaths)
            except yara.SyntaxError as e:
                test.add_fail('YARA', 'Failed to compile rules: {}'.format(str(e)))
                return

        # run analysis on the component and any shards
        for md in fw.mds:
            if md.blob:
                _run_on_blob(self, test, md, md.filename_contents, md.blob)
            for shard in md.shards:
                if shard.blob:
                    _run_on_blob(self, test, md, shard.name, shard.blob)

# run with PYTHONPATH=. ./env/bin/python3 plugins/blocklist/__init__.py
if __name__ == '__main__':
    import sys
    from lvfs.models import Firmware, Component

    plugin = Plugin('blocklist')
    _test = Test(plugin.id)
    _fw = Firmware()
    _md = Component()
    _md.blob = b'CN=DO NOT TRUST - AMI Test PK'
    _fw.mds.append(_md)
    plugin.run_test_on_fw(_test, _fw)
    for attribute in _test.attributes:
        print(attribute)
