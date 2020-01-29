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

from collections import namedtuple

from lvfs import db
from lvfs.pluginloader import PluginBase, PluginError, PluginSettingBool
from lvfs.models import Test, ComponentShard

INTELME_PART_ENTRY = '<4sIIIIIII'
INTELME_PART_HEADER = '<16s4sIBBBBHHII'

class PartitionEntry():

    def __init__(self):
        self.data = None
        self.blob = None

    def __str__(self):
        # flags defined in https://github.com/zamaudio/dump_me/blob/master/dump_me.py
        return str(self.data)

    def unpack_from(self, buf, offset):

        # Partition table header
        PartitionEntryTuple = namedtuple('PartitionEntryTuple',
                                         ['sig', 'owner', 'offset', 'len',
                                          'start_tokens', 'max_tokens',
                                          'scratch_sectors', 'flags'])
        self.data = PartitionEntryTuple._make(struct.unpack_from(INTELME_PART_ENTRY, buf, offset))

        if self.data.offset and self.data.len:
            self.blob = buf[self.data.offset:self.data.offset + self.data.len]

    @property
    def sig(self):
        if not self.data:
            return None
        if self.data.sig == b'\0\0\0\0':
            return None
        return self.data.sig.decode('ascii').replace('\x00', '')

    @property
    def appstream_id(self):
        if not self.sig:
            return None
        return 'com.intel.ManagementEngine.' + self.sig

    @property
    def guid(self):
        if not self.appstream_id:
            return None
        return str(uuid.uuid5(uuid.NAMESPACE_DNS, self.appstream_id))

class PartitionHeader():

    def __init__(self):
        self.data = None
        self.entries = []

    def __str__(self):
        tmp = str(self.data)
        for entry in self.entries:
            tmp += '\n * ' + str(entry)
        return tmp

    def unpack_from(self, buf, offset):

        # Partition table header
        PartitionHeaderTuple = namedtuple('PartitionHeaderTuple',
                                          ['vec', 'sig', 'entries', 'ver', 'type',
                                           'len', 'chk', 'life', 'lim',
                                           'uma_size', 'flags'])
        self.data = PartitionHeaderTuple._make(struct.unpack_from(INTELME_PART_HEADER, buf, offset))

        # sanity check
        if self.data.entries > 256:
            return

        # partition table entries
        offset += struct.calcsize(INTELME_PART_HEADER)
        offset += 8     # align
        for _ in range(0, self.data.entries):
            entry = PartitionEntry()
            entry.unpack_from(buf, offset)
            offset += struct.calcsize(INTELME_PART_ENTRY)
            self.entries.append(entry)

def _add_shards(self, fpt, md):

    # remove any old shards we added
    for shard in md.shards:
        if shard.plugin_id == self.id:
            db.session.delete(shard)
    db.session.commit()

    # add shards
    for entry in fpt.entries:
        if not entry.guid:
            continue
        if not entry.blob:
            continue
        shard = ComponentShard(component_id=md.component_id,
                               plugin_id=self.id,
                               guid=entry.guid,
                               name=entry.appstream_id)
        shard.set_blob(entry.blob, checksums='SHA256')
        md.shards.append(shard)

def _run_intelme_on_blob(self, test, md):

    # find and parse FPT
    offset = md.blob.find(b'$FPT')
    if offset == -1:
        # not an error if there's no ME...
        test.add_pass('No partition table header found')
        return
    offset -= 0x10

    # check signature
    fpt = PartitionHeader()
    try:
        fpt.unpack_from(md.blob[offset:], 0)
    except struct.error as e:
        test.add_fail('FPT invalid at {:#x}'.format(offset), str(e))
        return
    if fpt.data.sig != b'$FPT':
        test.add_fail('Signature invalid: ' + str(fpt.data.sig))
        return

    # check number of entries
    if not len(fpt.entries):
        test.add_pass('No entries -- possibly compression issue?')
        return

    # check version
    if fpt.data.ver in (0x0, 0xff):
        test.add_fail('Version {:#x} invalid'.format(fpt.data.ver))
        return

    # add shards to component
    _add_shards(self, fpt, md)

    # success
    entries = []
    for entry in fpt.entries:
        if entry.sig:
            entries.append(entry.sig)
    test.add_pass('Found {}'.format(','.join(entries)))

class Plugin(PluginBase):
    def __init__(self, plugin_id=None):
        PluginBase.__init__(self, plugin_id)
        self.name = 'Intel ME'
        self.summary = 'Analyse modules in Intel ME firmware'

    def settings(self):
        s = []
        s.append(PluginSettingBool('intelme_enabled', 'Enabled', True))
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
        return md.category.matches(['X-System', 'X-ManagementEngine'])

    def ensure_test_for_fw(self, fw):

        # add if not already exists
        test = fw.find_test_by_plugin_id(self.id)
        if not test:
            test = Test(self.id, waivable=True)
            fw.tests.append(test)

    def run_test_on_md(self, test, md):

        # run intelme on the capsule data
        _run_intelme_on_blob(self, test, md)
