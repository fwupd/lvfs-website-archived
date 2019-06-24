#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2019 Richard Hughes <richard@hughsie.com>
#
# SPDX-License-Identifier: GPL-2.0+
#
# pylint: disable=no-self-use

import tempfile
import glob
import os
import re
import subprocess
import zlib

from lvfs import db
from lvfs.pluginloader import PluginBase, PluginError, PluginSettingBool, PluginSettingText, PluginSettingInteger
from lvfs.models import Test, ComponentShard

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
        s.append(PluginSettingInteger('chipsec_size_min', 'Minimum size of shards', 0x80000))   # 512kb
        s.append(PluginSettingInteger('chipsec_size_max', 'Maximum size of shards', 0x2000000)) # 32Mb
        return s

    def _convert_files_to_shards(self, files):

        # parse each EFI binary as a shard
        shards = []
        for fn in files:
            sections = fn.rsplit('/')
            name = sections[-1].split('.')[0]
            kind = None
            guid = None
            for section in reversed(sections[:-1]):
                if section.find('GUID_DEFINED') != -1:
                    continue
                if section.find('COMPRESSION') != -1:
                    continue
                dirname_sections = section.split('.')
                guid = dirname_sections[0].split('_')[1].lower()
                kind = dirname_sections[1]
                break
            if not guid:
                continue
            appstream_kinds = {
                'FV_APPLICATION': 'Application',
                'FV_DRIVER': 'Driver',
                'FV_DXE_CORE': 'Dxe',
                'FV_PEI_CORE': 'Pei',
                'FV_PEIM': 'Peim',
                'FV_RAW': 'Raw',
                'FV_SECURITY_CORE': 'Security',
                'FV_COMBINED_PEIM_DRIVER': 'PeimDriver',
            }
            if kind in appstream_kinds:
                appstream_id = 'com.intel.Uefi.{}.{}'.format(appstream_kinds[kind], name)
            else:
                appstream_id = 'com.intel.Uefi.{}'.format(name)
            shard = ComponentShard(plugin_id=self.id)
            shard.ensure_info(guid, appstream_id)
            with open(fn, 'rb') as f:
                shard.set_blob(f.read())
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

    def _find_dell_pfs(self, blob):
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
                # only include blobs of a sane size
                if len(blob_decompressed) > self.get_setting_int('chipsec_size_min') and \
                   len(blob_decompressed) < self.get_setting_int('chipsec_size_max'):
                    return blob_decompressed
                offset_next += 2 + len(blob_decompressed)

            blob = blob[offset_next:]
            offset += offset_next

        return None

    def _run_chipsec_on_md(self, test, md):

        # remove any old shards we added
        for shard in md.shards:
            if shard.plugin_id == self.id:
                db.session.delete(shard)
        db.session.commit()

        # try first with the plain blob (possibly with a capsule header) and
        # then look for a Zlib section (with an optional PFS-prefixed) blob
        shards = self._get_shards_for_blob(md.blob)
        if not shards:
            blob = self._find_dell_pfs(md.blob)
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
            if self.get_setting_bool('chipsec_write_shards'):
                shard.save()
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
