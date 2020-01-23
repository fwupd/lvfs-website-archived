#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2019 Richard Hughes <richard@hughsie.com>
#
# SPDX-License-Identifier: GPL-2.0+
#
# pylint: disable=no-self-use,too-few-public-methods

import tempfile
import glob
import os
import re
import subprocess
import zlib
import uuid
import struct
from collections import namedtuple

from lvfs import db
from lvfs.pluginloader import PluginBase, PluginError, PluginSettingBool, PluginSettingText, PluginSettingInteger
from lvfs.models import Test, ComponentShard

class PfsFile:

    PFS_HEADER = '<8sII'
    PFS_FOOTER = '<II8s'
    PFS_SECTION = '<16sI4s8sQIIII16x'
    PFS_INFO = '<I16sHHHH4sH'

    def __init__(self, blob=None):
        self.shards = []
        self._names = {}
        if blob:
            self.parse(blob)

    def _parse_model(self, blob):
        pass

    def _parse_info(self, blob):
        off = 0
        while off < len(blob):
            nt = namedtuple('PfsInfoSection',
                            ['hdr_ver', 'guid', 'ver1', 'ver2', 'ver3', 'ver4', 'ver_type', 'charcnt'])
            try:
                pfs_info = nt._make(struct.unpack_from(PfsFile.PFS_INFO, blob, off))
            except struct.error as e:
                raise RuntimeError(str(e))
            if pfs_info.hdr_ver != 1:
                raise RuntimeError('PFS info version %i unsupported' % pfs_info.hdr_ver)
            guid = str(uuid.UUID(bytes_le=pfs_info.guid))
            off += struct.calcsize(PfsFile.PFS_INFO)
            self._names[guid] = blob[off:off+pfs_info.charcnt*2].decode("utf-16-le")
            off += pfs_info.charcnt*2 + 2

    def parse(self, blob):

        # sanity check
        nt = namedtuple('PfsHeaderTuple', ['tag', 'hdr_ver', 'payload_size'])
        try:
            pfs_hdr = nt._make(struct.unpack_from(PfsFile.PFS_HEADER, blob, 0x0))
        except struct.error as e:
            raise RuntimeError(str(e))
        if pfs_hdr.tag != b'PFS.HDR.':
            raise RuntimeError('Not a PFS header')
        if pfs_hdr.hdr_ver != 1:
            raise RuntimeError('PFS header version %i unsupported' % pfs_hdr.hdr_ver)

        # parse sections
        offset = struct.calcsize(PfsFile.PFS_HEADER)
        while offset < len(blob) - struct.calcsize(PfsFile.PFS_FOOTER):

            # parse the section
            nt = namedtuple('PfsHeaderSection',
                            ['guid', 'hdr_ver', 'ver_type',
                             'version', 'reserved', 'data_sz', 'data_sig_sz',
                             'metadata_sz', 'metadata_sig_sz'])
            try:
                pfs_sect = nt._make(struct.unpack_from(PfsFile.PFS_SECTION, blob, offset))
            except struct.error as e:
                raise RuntimeError(str(e))
            if pfs_sect.hdr_ver != 1:
                raise RuntimeError('PFS section version %i unsupported' % pfs_hdr.hdr_ver)
            offset += struct.calcsize(PfsFile.PFS_SECTION)

            # parse the data and ignore the rest
            shard = ComponentShard()
            shard.set_blob(blob[offset:offset+pfs_sect.data_sz])
            shard.guid = str(uuid.UUID(bytes_le=pfs_sect.guid))
            if shard.guid == 'fd041960-0dc8-4b9f-8225-bba9e37c71e0':
                self._parse_info(shard.blob)
            elif shard.guid == '233ae3fb-da68-4fd4-92cb-a6229a611d6f':
                self._parse_model(shard.blob)
            else:
                self.shards.append(shard)

            # advance to the next section
            offset += pfs_sect.data_sz
            offset += pfs_sect.data_sig_sz
            offset += pfs_sect.metadata_sz
            offset += pfs_sect.metadata_sig_sz

        # the INFO structure is typically last, so fix up added shards
        for shard in self.shards:
            if shard.guid in self._names:
                shard.name = 'com.dell.' + self._names[shard.guid].replace(' ', '')
            else:
                shard.name = 'com.dell.' + shard.guid

class Plugin(PluginBase):
    def __init__(self, plugin_id=None):
        PluginBase.__init__(self, plugin_id)
        self.name = 'CHIPSEC'
        self.summary = 'Add firmware shards for UEFI capsules'

    def settings(self):
        s = []
        s.append(PluginSettingBool('chipsec_enabled', 'Enabled', True))
        s.append(PluginSettingBool('chipsec_write_shards', 'Write shards to disk', True))
        s.append(PluginSettingText('chipsec_binary', 'CHIPSEC executable', 'chipsec_util'))
        s.append(PluginSettingInteger('chipsec_size_min', 'Minimum size of shards', 0x80000))   # 512kb
        s.append(PluginSettingInteger('chipsec_size_max', 'Maximum size of shards', 0x4000000)) # 64Mb
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
            shard = ComponentShard(plugin_id=self.id, name=appstream_id, guid=guid)
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
        try:
            # pylint: disable=unexpected-keyword-arg
            subprocess.check_output([cmd, '--no_driver', 'uefi', 'decode', src.name],
                                    stderr=subprocess.PIPE,
                                    cwd=cwd.name)
        except subprocess.CalledProcessError as e:
            raise PluginError('Failed to decode file: {}'.format(e.output))

        # look for shards
        outdir = src.name + '.dir'
        files = glob.glob(outdir + '/FV/**/*.efi', recursive=True)
        files.extend(glob.glob(outdir + '/FV/**/*.pe32', recursive=True))
        return self._convert_files_to_shards(files)

    def _find_zlib_sections(self, blob):
        offset = 0
        sections = []
        while 1:
            # find Zlib header for default compression
            offset = blob.find(b'\x78\x9C', offset)
            if offset == -1:
                break

            # decompress the buffer, which also checks if it's really Zlib or just
            # two random bytes that happen to match for no good reason
            try:
                obj = zlib.decompressobj()
                blob_decompressed = obj.decompress(blob[offset:])
                offset = len(blob) - len(obj.unused_data)
            except zlib.error as _:
                offset += 2
            else:
                # only include blobs of a sane size
                if len(blob_decompressed) > self.get_setting_int('chipsec_size_min') and \
                   len(blob_decompressed) < self.get_setting_int('chipsec_size_max'):
                    sections.append(blob_decompressed)
        return sections

    def _run_chipsec_on_md(self, test, md):

        # remove any old shards we added
        for shard in md.shards:
            if shard.plugin_id == self.id:
                for result in shard.yara_query_results:
                    db.session.delete(result)
                db.session.delete(shard)
        db.session.commit()

        # try first with the plain blob (possibly with a capsule header) and
        # then look for a Zlib section (with an optional PFS-prefixed) blob
        shards = self._get_shards_for_blob(md.blob)
        if not shards:
            for blob in self._find_zlib_sections(md.blob):
                try:
                    pfs = PfsFile(blob)
                    for shard in pfs.shards:
                        shards.append(shard)
                        shards.extend(self._get_shards_for_blob(shard.blob))
                    test.add_pass('Found PFS in Zlib compressed blob')
                except RuntimeError as _:
                    shard = ComponentShard(plugin_id=self.id)
                    shard.set_blob(blob)
                    shard.name = 'Zlib'
                    shard.guid = '68b8cc0e-4664-5c7a-9ce3-8ed9b4ffbffb'
                    shards.append(shard)
                    shards.extend(self._get_shards_for_blob(shard.blob))
                    test.add_pass('Found Zlib compressed blob')
        if not shards:
            test.add_pass('No firmware volumes found in {}'.format(md.filename_contents))
            return

        # add shard to component
        for shard in shards:
            shard.plugin_id = self.id
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
