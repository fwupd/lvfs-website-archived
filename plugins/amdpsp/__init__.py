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

from psptool import PSPTool
from psptool.entry import PubkeyEntry, HeaderEntry
from psptool.blob import Blob

from lvfs import db
from lvfs.pluginloader import PluginBase, PluginError, PluginSettingBool
from lvfs.models import Test, ComponentShard

def _mkguid(value):
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
    except Blob.NoFirmwareEntryTableError as _:
        pass

class Plugin(PluginBase):
    def __init__(self, plugin_id=None):
        PluginBase.__init__(self, plugin_id)
        self.name = 'AMD PSP'
        self.summary = 'Analyse modules in AMD PSP firmware'

    def settings(self):
        s = []
        s.append(PluginSettingBool('amdpsp_enabled', 'Enabled', True))
        return s

    def _require_test_for_md(self, md):

        # match on protocol
        if not md.protocol:
            # only until required
            return True
        if md.protocol.value != 'org.uefi.capsule':
            return False

        # match on category
        if not md.category:
            # only until required
            return True
        return md.category.matches(['X-System', 'X-PlatformSecurityProcessor'])

    def _require_test_for_fw(self, fw):
        for md in fw.mds:
            if self._require_test_for_md(md):
                return True
        return False

    def ensure_test_for_fw(self, fw):

        # add if not already exists
        if self._require_test_for_fw(fw):
            test = fw.find_test_by_plugin_id(self.id)
            if not test:
                test = Test(self.id, waivable=True)
                fw.tests.append(test)

    def run_test_on_md(self, test, md):

        # run psptool on the capsule data
        if not md.blob:
            return
        if self._require_test_for_md(md):
            _run_psptool_on_blob(self, test, md)
        db.session.commit()
