#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2019 Richard Hughes <richard@hughsie.com>
# Licensed under the GNU General Public License Version 2
#
# pylint: disable=no-self-use

import tempfile
import glob
import os
import re
import subprocess
import zlib

from app import db
from app.pluginloader import PluginBase, PluginError, PluginSettingBool, PluginSettingText
from app.models import Test, ComponentShard

def _find_dell_pfs(blob):
    offset = 0

    while 1:
        # find Zlib header for default compression
        offset_next = blob.find(b'\x78\x9C')
        if offset_next == -1:
            break

        # decompress the buffer, which also checks if it's really Zlib or just
        # two random bytes that happen to match for no good reason
        try:
            blob_decompressed = zlib.decompress(blob[offset_next:])
        except zlib.error as _:
            offset_next += 2
        else:
            # only include blobs greater than 512kB in size
            if len(blob_decompressed) > 0x80000:
                return blob_decompressed
            offset_next += 2 + len(blob_decompressed)

        blob = blob[offset_next:]
        offset += offset_next

    return None

class Plugin(PluginBase):
    def __init__(self, plugin_id=None):
        PluginBase.__init__(self, plugin_id)

    def name(self):
        return 'CHIPSEC'

    def summary(self):
        return 'Add firmware shards for UEFI capsules'

    def settings(self):
        s = []
        s.append(PluginSettingBool('chipsec_enabled', 'Enabled', True))
        s.append(PluginSettingBool('chipsec_write_shards', 'Write shards to disk', True))
        s.append(PluginSettingText('chipsec_binary', 'CHIPSEC executable', 'chipsec_util'))
        return s

    def _convert_files_to_shards(self, files):

        # should we write to disk for later processing
        save = self.get_setting_bool('chipsec_write_shards')

        # parse each EFI binary as a shard
        shards = []
        for fn in files:
            sections = fn.rsplit('/')
            name = sections[-1].split('.')[0]
            guid = None
            for section in reversed(sections[:-1]):
                if section.find('GUID_DEFINED') != -1:
                    continue
                if section.find('COMPRESSION') != -1:
                    continue
                guid = section.split('_')[1].split('.')[0].lower()
                break
            if not guid:
                continue

            shard = ComponentShard(plugin_id=self.id)
            shard.ensure_info(guid, name)
            with open(fn, 'rb') as f:
                shard.set_blob(f.read(), save=save)
            shards.append(shard)
        return shards

    def _get_shards_for_blob(self, blob):

        # write blob to temp file
        cwd = tempfile.TemporaryDirectory(prefix='lvfs')
        src = tempfile.NamedTemporaryFile(mode='wb',
                                          prefix='lvfs_',
                                          suffix=".bin",
                                          dir=cwd.name,
                                          delete=False)
        src.write(blob)
        src.flush()

        # run chipsec
        cmd = self.get_setting('chipsec_binary', required=True)
        argv = [cmd, '--no_driver', 'uefi', 'decode', src.name]
        ps = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=cwd.name)
        if ps.wait() != 0:
            raise PluginError('Failed to decode file: %s' % ps.stderr.read())

        # look for shards
        outdir = src.name + '.dir'
        files = glob.glob(outdir + '/FV/**/*.efi', recursive=True)
        return self._convert_files_to_shards(files)

    def _run_chipsec_on_md(self, test, md):

        # remove any old shards we added
        for shard in md.shards:
            if shard.plugin_id == self.id:
                db.session.delete(shard)

        # try first with the plain blob (possibly with a capsule header) and
        # then look for a Zlib section (with an optional PFS-prefixed) blob
        shards = self._get_shards_for_blob(md.blob)
        if not shards:
            blob = _find_dell_pfs(md.blob)
            if blob:
                if blob.startswith(b'PFS.HDR.'):
                    test.add_pass('Found PFS in Zlib compressed blob')
                    # don't parse the PFS as chipsec just does blob.find('_FVH')
                    # anyway: https://github.com/LongSoft/PFSExtractor
                else:
                    test.add_pass('Found Zlib compressed blob')
                shards = self._get_shards_for_blob(blob)
        if not shards:
            test.add_pass('No firmware volumes found in {}'.format(md.filename_contents))
            return

        # add shard to component
        for shard in shards:
            shard.component_id = md.component_id
            md.shards.append(shard)

    def _require_test_for_md(self, md):
        if not md.protocol:
            return False
        return md.protocol.value == 'org.uefi.capsule'

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

    def run_test_on_fw(self, test, fw):

        # run chipsec on the capsule data
        for md in fw.mds:
            if not self._require_test_for_md(md):
                continue
            if not md.blob:
                continue
            self._run_chipsec_on_md(test, md)
        db.session.commit()

# run with PYTHONPATH=. ./.env3/bin/python3 plugins/chipsec/__init__.py ./firmware.bin
if __name__ == '__main__':
    import sys
    from app.models import Firmware, Component, Protocol

    for _argv in sys.argv[1:]:
        print('Processing', _argv)
        plugin = Plugin('chipsec')
        _test = Test(plugin.id)
        _fw = Firmware()
        _md = Component()
        _md.filename_contents = 'filename.bin'
        _md.protocol = Protocol('org.uefi.capsule')
        with open(_argv, 'rb') as _f:
            _md.blob = _f.read()
        _fw.mds.append(_md)
        plugin.run_test_on_fw(_test, _fw)
        for attribute in _test.attributes:
            print(attribute)
        print(_md.shards)
