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
import datetime

# allows us to run this from the project root
sys.path.append(os.path.realpath('.'))

from lvfs.models import Test, Firmware, Component, Protocol, ComponentShard
from plugins.pecheck import Plugin

if __name__ == '__main__':
    for _argv in sys.argv[1:]:
        print('Processing', _argv)
        plugin = Plugin('pecheck')
        _test = Test(plugin_id=plugin.id)
        _fw = Firmware()
        _fw.timestamp = datetime.datetime.utcnow()
        _md = Component()
        _md.protocol = Protocol(value='org.uefi.capsule')
        _shard = ComponentShard(name=os.path.basename(_argv))
        try:
            with open(_argv, 'rb') as f:
                _shard.set_blob(f.read())
        except IsADirectoryError as _:
            continue
        _md.shards.append(_shard)
        plugin.run_test_on_md(_test, _md)
        for attribute in _test.attributes:
            print(attribute)
        for cert in _shard.certificates:
            print(cert)
