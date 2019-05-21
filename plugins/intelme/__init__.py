#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2019 Richard Hughes <richard@hughsie.com>
# Licensed under the GNU General Public License Version 2
#
# pylint: disable=no-self-use,no-member,too-few-public-methods

import os
import struct
import uuid
import hashlib

from collections import namedtuple

from app import db
from app.pluginloader import PluginBase, PluginError, PluginSettingBool
from app.models import Test, ComponentShard, ComponentShardChecksum, ComponentShardInfo

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
        self.data = PartitionEntryTuple._make(struct.unpack_from('<4sIIIIIII', buf, offset))

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
        return uuid.uuid5(uuid.NAMESPACE_DNS, self.appstream_id)

    @property
    def sha256(self):
        if not self.blob:
            return None
        return hashlib.sha256(self.blob).hexdigest()

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
                                          ['sig', 'entries', 'ver', 'type',
                                           'len', 'chk', 'life', 'lim',
                                           'uma_size', 'flags'])
        self.data = PartitionHeaderTuple._make(struct.unpack_from('<16x4sIBBBBHHII', buf, offset))

        # sanity check
        if self.data.entries > 256:
            return

        # partition table entries
        offset += 0x30
        for _ in range(0, self.data.entries):
            entry = PartitionEntry()
            entry.unpack_from(buf, offset)
            offset += 0x20
            self.entries.append(entry)

def _add_shards(fpt, md):

    # remove any old shards
    for shard in md.shards:
        db.session.delete(shard)

    # add shards
    for entry in fpt.entries:
        if not entry.guid:
            continue
        if not entry.sha256:
            continue
        shard = ComponentShard(component_id=md.component_id)
        shard.blob = entry.blob
        shard.info = db.session.query(ComponentShardInfo).\
                            filter(ComponentShardInfo.guid == entry.guid).first()
        if shard.info:
            shard.info.cnt += 1
        else:
            shard.info = ComponentShardInfo(entry.guid, entry.appstream_id)
        csum = ComponentShardChecksum(entry.sha256, 'SHA256')
        shard.checksums.append(csum)
        md.shards.append(shard)

def _run_intelme_on_blob(test, md):

    # find and parse FPT
    offset = md.blob.find(b'$FPT')
    if offset == -1:
        # not an error if there's no ME...
        test.add_pass('Offset', 'No partition table header found, ignoring')
        return
    offset -= 0x10
    test.add_pass('Offset', '{:#x}'.format(offset))

    # check signature
    fpt = PartitionHeader()
    try:
        fpt.unpack_from(md.blob[offset:], 0)
    except struct.error as e:
        test.add_fail('FPT', str(e))
        return
    if fpt.data.sig != b'$FPT':
        test.add_fail('Signature', 'Invalid: ' + str(fpt.data.sig))
        return

    # check number of entries
    if not len(fpt.entries):
        test.add_pass('Entries', 'Possibly compression issue?')
        return

    # check version
    if fpt.data.ver in (0x0, 0xff):
        test.add_fail('Version', 'Version {:#x} invalid'.format(fpt.data.ver))
        return

    # add shards to component
    _add_shards(fpt, md)

    # success
    entries = []
    for entry in fpt.entries:
        if entry.sig:
            entries.append(entry.sig)
    test.add_pass('Found', ','.join(entries))

def _require_test(md):

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
    return md.category.matches(['X-System', 'X-ManagementEngine'])

class Plugin(PluginBase):
    def __init__(self):
        PluginBase.__init__(self)

    def name(self):
        return 'Intel ME'

    def summary(self):
        return 'Analyse modules in Intel ME firmware'

    def settings(self):
        s = []
        s.append(PluginSettingBool('intelme_enabled', 'Enabled', True))
        return s

    def ensure_test_for_fw(self, fw):

        # only run for capsule updates
        require_test = False
        for md in fw.mds:
            if _require_test(md):
                require_test = True
                break

        # add if not already exists
        if require_test:
            test = fw.find_test_by_plugin_id(self.id)
            if not test:
                test = Test(self.id, waivable=True)
                fw.tests.append(test)

    def run_test_on_fw(self, test, fw):

        # run intelme on the capsule data
        for md in fw.mds:
            if _require_test(md):
                _run_intelme_on_blob(test, md)
        db.session.commit()

# run with PYTHONPATH=. ./.env3/bin/python3 plugins/intelme/__init__.py ./firmware.bin
if __name__ == '__main__':
    import sys
    from app.models import Firmware, Component, Protocol, Category

    plugin = Plugin()
    _test = Test('intelme')
    _fw = Firmware()
    _md = Component()
    _md.protocol = Protocol('org.uefi.capsule')
    _md.category = Category('X-ManagementEngine')
    _fw.mds.append(_md)

    with open(sys.argv[1], 'rb') as f:
        _md.blob = f.read()
    plugin.run_test_on_fw(_test, _fw)
    for attribute in _test.attributes:
        print(attribute)
    for _shard in _md.shards:
        if not _shard.checksums:
            continue
        print(_shard.checksums[0])
