#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2019 Richard Hughes <richard@hughsie.com>
#
# SPDX-License-Identifier: GPL-2.0+
#
# pylint: disable=no-self-use,no-member,too-few-public-methods

import os
import struct
import uuid
from typing import Optional

from psptool import PSPTool
from psptool.entry import PubkeyEntry, HeaderEntry
from psptool.blob import Blob

from lvfs import db
from lvfs.pluginloader import PluginBase, PluginError, PluginSettingBool
from lvfs.tests.models import Test
from lvfs.components.models import ComponentShard

def _mkguid(value: str) -> Optional[str]:
    if not value:
        return None
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, value))

def _get_readable_type(entry):
    if not entry.type in entry.DIRECTORY_ENTRY_TYPES:
        return hex(entry.type)
    return entry.DIRECTORY_ENTRY_TYPES[entry.type].replace('!', '')

def _run_psptool_on_blob(self, test, md):

    # remove any old shards we added
    for shard in md.shards:
        if shard.plugin_id == self.id:
            db.session.delete(shard)
    db.session.commit()

    # parse firmware
    try:
        psp = PSPTool(md.blob, verbose=True)
        for directory in psp.blob.directories:
            for entry in directory.entries:
                if isinstance(entry, HeaderEntry):
                    blob = entry.get_decompressed()
                    appstream_id = 'com.amd.PSP.HeaderEntry.{}'.\
                                        format(_get_readable_type(entry))
                elif isinstance(entry, PubkeyEntry):
                    blob = entry.get_pem_encoded()
                    appstream_id = 'com.amd.PSP.Entry.{}'.\
                                        format(_get_readable_type(entry))
                else:
                    blob = entry.get_bytes()
                    appstream_id = 'com.amd.PSP.{}'.\
                                        format(_get_readable_type(entry))

                # add shard to component
                shard = ComponentShard(component_id=md.component_id,
                                       plugin_id=self.id,
                                       guid=_mkguid(hex(entry.type)),
                                       name=appstream_id)
                shard.set_blob(blob, checksums='SHA256')
                md.shards.append(shard)
        test.add_pass('Found {} directories'.format(len(psp.blob.directories)))
    except (Blob.NoFirmwareEntryTableError, AssertionError) as _:
        pass

class Plugin(PluginBase):
    def __init__(self):
        PluginBase.__init__(self)
        self.name = 'AMD PSP'
        self.summary = 'Analyse modules in AMD PSP firmware'

    def settings(self):
        s = []
        s.append(PluginSettingBool('amdpsp_enabled', 'Enabled', True))
        return s

    def require_test_for_md(self, md):

        # match on protocol
        if not md.protocol:
            return False
        if md.protocol.value != 'org.uefi.capsule':
            return False
        if not md.blob:
            return False

        # match on category
        if not md.category:
            return True
        return md.category.matches(['X-System', 'X-PlatformSecurityProcessor'])

    def ensure_test_for_fw(self, fw):

        # add if not already exists
        test = fw.find_test_by_plugin_id(self.id)
        if not test:
            test = Test(plugin_id=self.id, waivable=True)
            fw.tests.append(test)

    def run_test_on_md(self, test, md):

        # run psptool on the capsule data
        _run_psptool_on_blob(self, test, md)
        db.session.commit()

# run with PYTHONPATH=. ./env/bin/python3 plugins/amdpsp/__init__.py
if __name__ == '__main__':
    import sys

    from lvfs.categories.models import Category
    from lvfs.components.models import Component
    from lvfs.firmware.models import Firmware
    from lvfs.protocols.models import Protocol

    for _argv in sys.argv[1:]:
        print('Processing', _argv)
        plugin = Plugin()
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
        for _shard in _md.shards:
            print(_shard.guid, _shard.name, _shard.checksum, len(_shard.blob))
