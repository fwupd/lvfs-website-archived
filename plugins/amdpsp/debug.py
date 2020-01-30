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

from lvfs.models import Test, Firmware, Component, Protocol, Category
from plugins.amdpsp import Plugin

if __name__ == '__main__':
    for _argv in sys.argv[1:]:
        print('Processing', _argv)
        plugin = Plugin('amdpsp')
        _test = Test(plugin_id=plugin.id)
        _fw = Firmware()
        _md = Component()
        _md.component_id = 999999
        _md.category = Category(value='X-PlatformSecurityProcessor')
        _md.filename_contents = 'filename.bin'
        _md.protocol = Protocol(value='org.uefi.capsule')
        with open(_argv, 'rb') as _f:
            _md.blob = _f.read()
        plugin.run_test_on_md(_test, _md)
        for attribute in _test.attributes:
            print(attribute)
        for shard in _md.shards:
            print(shard.guid, shard.name, shard.checksum, len(shard.blob))
