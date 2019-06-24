#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2019 Richard Hughes <richard@hughsie.com>
#
# SPDX-License-Identifier: GPL-2.0+
#
# pylint: disable=protected-access,wrong-import-position

import os
import sys

# allows us to run this from the project root
sys.path.append(os.path.realpath('.'))

from lvfs.models import Test, Firmware, Component, Protocol
from plugins.chipsec import Plugin

if __name__ == '__main__':
    for _argv in sys.argv[1:]:
        print('Processing', _argv)
        plugin = Plugin('chipsec')
        _test = Test(plugin.id)
        _fw = Firmware()
        _md = Component()
        _md.component_id = 999999
        _md.filename_contents = 'filename.bin'
        _md.protocol = Protocol('org.uefi.capsule')
        with open(_argv, 'rb') as _f:
            _md.blob = _f.read()
        _fw.mds.append(_md)
        plugin.run_test_on_fw(_test, _fw)
        for attribute in _test.attributes:
            print(attribute)
        for shard in _md.shards:
            print(shard.info.guid, shard.info.name, shard.checksum)
