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
from lvfs.models import Test, ComponentShard, ComponentShardAttribute

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
                raise RuntimeError from e
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
            raise RuntimeError from e
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
                raise RuntimeError from e
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

class InfoTxtFile:

    def __init__(self, blob=None):
        self._data = {}
        if blob:
            self.parse(blob)

    def parse(self, blob):
        for line in blob.decode().split('\n'):
            try:
                k, v = line.split(': ', maxsplit=1)
                self._data[k] = v
            except ValueError as _:
                pass

    def get(self, key):
        return self._data.get(key)

    def get_int(self, key):
        value = self.get(key)
        if not value:
            return None
        for split in [',', ' ']:
            value = value.split(split)[0]
        if value.endswith('h'):
            return int(value[:-1], 16)
        return int(value)


class PfatFile:

    PFAT_HEADER = '<II8sB'
    PFAT_BLOCK_HEADER = '<I16sIIIIIII'
    PFAT_BLOCK_SIGN = '<II64II64I'

    def __init__(self, blob=None):
        self.shards = []
        if blob:
            self.parse(blob)

    def parse(self, blob):

        # sanity check
        PfatHeader = namedtuple('PfatHeader', ['size', 'csum', 'tag', 'ctrl'])
        try:
            pfat_hdr = PfatHeader._make(
                struct.unpack_from(PfatFile.PFAT_HEADER, blob, 0x0)
            )
        except struct.error as e:
            raise RuntimeError from e
        if pfat_hdr.tag != b'_AMIPFAT':
            raise RuntimeError('Not a PFAT header')

        # parse the header data which seems to be of the form:
        # "1 /B 4 ;BIOS_FV_BB.bin" where the blockcount is 4 in this example
        section_data = (
            blob[struct.calcsize(PfatFile.PFAT_HEADER) : pfat_hdr.size]
            .decode('utf-8')
            .splitlines()
        )
        PfatSection = namedtuple(
            'PfatSection', ['flash', 'param', 'blockcnt', 'filename']
        )
        sections = []
        for entry in section_data[1:]:
            entry_data = entry.split(' ')
            sections.append(
                PfatSection(
                    flash=int(entry_data[0]),
                    param=entry_data[1],
                    blockcnt=int(entry_data[2]),
                    filename=entry_data[3][1:],
                )
            )

        # parse sections
        offset = pfat_hdr.size
        for section in sections:
            data = b''
            for _ in range(section.blockcnt):
                PfatBlockHeader = namedtuple(
                    'PfatBlockHeader',
                    [
                        'revision',
                        'platform',
                        'unknown0',
                        'unknown1',
                        'flagsz',
                        'datasz',
                        'unknown2',
                        'unknown3',
                        'unknown4',
                    ],
                )
                block_hdr = PfatBlockHeader._make(
                    struct.unpack_from(PfatFile.PFAT_BLOCK_HEADER, blob, offset)
                )
                block_data_start = (
                    offset
                    + struct.calcsize(PfatFile.PFAT_BLOCK_HEADER)
                    + block_hdr.flagsz
                )
                data += blob[block_data_start : block_data_start + block_hdr.datasz]
                offset += (
                    struct.calcsize(PfatFile.PFAT_BLOCK_HEADER)
                    + block_hdr.flagsz
                    + block_hdr.datasz
                    + struct.calcsize(PfatFile.PFAT_BLOCK_SIGN)
                )

            # add shard blob
            shard = ComponentShard()
            shard.set_blob(data)
            shard.name = 'com.ami.' + section.filename
            shard.guid = uuid.uuid3(uuid.NAMESPACE_DNS, section.filename)
            self.shards.append(shard)


class Plugin(PluginBase):
    def __init__(self, plugin_id=None):
        PluginBase.__init__(self, plugin_id)
        self.name = 'UEFI Extract'
        self.summary = 'Add firmware shards for UEFI capsules'

    def settings(self):
        s = []
        s.append(PluginSettingBool('uefi_extract_enabled', 'Enabled', True))
        s.append(PluginSettingBool('uefi_extract_write_shards', 'Write shards to disk', True))
        s.append(PluginSettingText('uefi_extract_binary', 'UEFIExtract executable', 'UEFIExtract'))
        s.append(PluginSettingInteger('uefi_extract_size_min', 'Minimum size of shards', 0x80000))   # 512kb
        s.append(PluginSettingInteger('uefi_extract_size_max', 'Maximum size of shards', 0x4000000)) # 64Mb
        return s

    def _convert_files_to_shards(self, files):

        # parse each EFI binary as a shard
        shards = []
        shard_by_checksum = {}
        for fn in files:
            dirname = os.path.dirname(fn)
            try:
                with open(os.path.join(dirname, 'body.bin'), 'rb') as f:
                    payload = f.read()
            except FileNotFoundError as _:
                continue
            if len(payload) < 0x100:
                #print('ignoring payload of {} bytes'.format(len(payload)))
                continue

            # read in child data
            with open(fn, 'rb') as f:
                data = InfoTxtFile(f.read())
            if data.get('Subtype') in ['PE32 image', 'TE image']:
                with open(os.path.join(dirname, '..', 'info.txt'), 'rb') as f:
                    data = InfoTxtFile(f.read())
            name = data.get('Text')
            if not name:
                if data.get('CPU signature') and data.get('CPU flags'):
                    name = '{:08X}.{:08X}'.format(data.get_int('CPU signature'),
                                                  data.get_int('CPU flags'))
            if name:
                for src in [' ', '(', ')']:
                    name = name.replace(src, '_')
            kind = data.get('Type')
            subkind = data.get('Subtype')
            guid = data.get('File GUID')
            if guid:
                guid = guid.lower()
            if subkind:
                kind += '::' + subkind

            # generate something plausible
            if kind == 'Microcode::Intel':
                guid = '3f0229ad-0a00-5269-90cf-0a45d8781b72'
            if not guid:
                #print('No GUID for', kind, fn)
                continue

            # ignore some kinds
            appstream_kinds = {
                '00h::Unknown 0': None,
                '01h::Compressed': None,
                '01h::Raw': None,
                '02h::Freeform': None,
                '02h::GUID defined': 'com.intel.Uefi.Raw',
                '03h::SEC core': 'com.intel.Uefi.Security',
                '04h::PEI core': 'com.intel.Uefi.Pei',
                '05h::DXE core': 'com.intel.Uefi.Dxe',
                '06h::PEI module': 'com.intel.Uefi.Peim',
                '07h::DXE driver': 'com.intel.Uefi.Driver',
                '09h::Application': 'com.intel.Uefi.Application',
                '0Ah::SMM module': 'com.intel.Uefi',
                '0Bh::Volume image': None,
                '0Ch::Combined SMM/DXE': 'com.intel.Uefi.SmmDxe',
                '0Dh::SMM core': 'com.intel.Uefi',
                '12h::TE image': None,
                '13h::DXE dependency': None,
                '14h::Version': None,
                '15h::UI': None,
                '17h::Volume image': None,
                '18h::Freeform subtype GUID': None,
                '19h::Raw': None,
                '1Bh::PEI dependency': None,
                '1Ch::MM dependency': None,
                'BPDT store': None,
                'CPD entry': None,
                'CPD partition::Code': None,
                'CPD partition::Key': None,
                'CPD partition::Manifest': None,
                'CPD partition::Metadata': None,
                'CPD store': None,  # ??
                'ECh': None,
                'EDh::GUID': None,
                'EEh::Name': None,
                'EFh::Data': None,
                'F0h::Pad': None,
                'Free space': None,
                'FTW store': None,
                'Image::Intel': None,
                'Image::UEFI': None,
                'Microcode::Intel': 'com.intel.Microcode',
                'NVAR entry::Full': None,
                'Padding::Empty (0xFF)': None,
                'Padding::Non-empty': None,
                'Region::BIOS': None,
                'Region::Descriptor': None,
                'Region::DevExp1': None,
                'Volume::FFSv2': None,
                'Volume::NVRAM': 'com.intel.Uefi.NVRAM',
                'VSS2 store': None,
            }
            if kind not in appstream_kinds:
                if len(kind) > 3:
                    print('No appstream_kinds for', kind, fn)
                continue
            if not appstream_kinds[kind]:
                #print('Ignoring appstream kind', kind)
                continue

            # something plausible
            appstream_id = appstream_kinds[kind]
            if name:
                appstream_id += '.{}'.format(name)
            shard = ComponentShard(plugin_id=self.id, name=appstream_id, guid=guid)
            shard.set_blob(payload)

            # do not add duplicates!
            if shard.checksum in shard_by_checksum:
                #print('skipping duplicate {}'.format(guid))
                continue

            # add attributes
            if kind == 'Microcode::Intel':

                # e.g. 000806E9
                value = data.get_int('CPU signature')
                if value:
                    shard.attributes.append(ComponentShardAttribute(key='cpuid',
                                                                    value='{:08X}'.format(value)))

                # e.g. C0
                value = data.get_int('CPU flags')
                if value:
                    shard.attributes.append(ComponentShardAttribute(key='platform',
                                                                    value='{:08X}'.format(value)))

                # e.g. C6
                value = data.get_int('Revision')
                if value:
                    shard.attributes.append(ComponentShardAttribute(key='version',
                                                                    value='{:08X}'.format(value)))

                # convert dd.mm.yyyy to yyyymmdd
                value = data.get('Date')
                if value:
                    split = value.split('.')
                    date_iso = '{}{}{}'.format(split[2], split[1], split[0])
                    shard.attributes.append(ComponentShardAttribute(key='yyyymmdd', value=date_iso))

                # combined size of header and body
                sz_bdy = data.get_int('Full size')
                sz_hdr = data.get_int('Header size')
                if sz_bdy and sz_hdr:
                    value = sz_bdy + sz_hdr
                    shard.attributes.append(ComponentShardAttribute(key='size',
                                                                    value='{:08X}'.format(value)))

                # e.g. 98458A98
                value = data.get_int('Checksum')
                if value:
                    shard.attributes.append(ComponentShardAttribute(key='checksum',
                                                                    value='{:08X}'.format(value)))

            shard_by_checksum[shard.checksum] = shard
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

        # run UEFIExtract
        cmd = self.get_setting('uefi_extract_binary', required=True)
        try:
            # pylint: disable=unexpected-keyword-arg
            subprocess.check_output([cmd, src.name],
                                    stderr=subprocess.PIPE,
                                    cwd=cwd.name)
        except subprocess.CalledProcessError as e:
            raise PluginError('Failed to decode file') from e

        # look for shards
        files = glob.glob(src.name + '.dump' + '/**/info.txt', recursive=True)
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
                if len(blob_decompressed) > self.get_setting_int('uefi_extract_size_min') and \
                   len(blob_decompressed) < self.get_setting_int('uefi_extract_size_max'):
                    sections.append(blob_decompressed)
        return sections

    def _run_uefi_extract_on_md(self, test, md):

        # remove any old shards we added
        for shard in md.shards:
            if shard.plugin_id == self.id:
                for result in shard.yara_query_results:
                    db.session.delete(result)
                db.session.delete(shard)
        db.session.commit()

        # is this a AMI BIOS with PFAT sections
        if md.blob[8:16] == b'_AMIPFAT':
            pfat = PfatFile(md.blob)
            shards = []
            for shard in pfat.shards:
                shards.append(shard)
                if shard.name == 'com.ami.BIOS_FV_BB.bin':
                    continue
                shards.extend(self._get_shards_for_blob(shard.blob))
            test.add_pass('Found PFAT blob')

        # try with the plain blob (possibly with a capsule header) and
        # then look for a Zlib section (with an optional PFS-prefixed) blob
        else:
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
            if self.get_setting_bool('uefi_extract_write_shards'):
                shard.save()
            md.shards.append(shard)

    def require_test_for_md(self, md):
        if not md.protocol:
            return False
        if not md.blob:
            return False
        return md.protocol.value == 'org.uefi.capsule'

    def ensure_test_for_fw(self, fw):

        # add if not already exists
        test = fw.find_test_by_plugin_id(self.id)
        if not test:
            test = fw.find_test_by_plugin_id('chipsec') # old name
        if not test:
            test = Test(plugin_id=self.id, waivable=True)
            fw.tests.append(test)

    def run_test_on_md(self, test, md):

        # extract the capsule data
        self._run_uefi_extract_on_md(test, md)

# run with PYTHONPATH=. ./env/bin/python3 plugins/uefi-extract/__init__.py
if __name__ == '__main__':
    import sys
    from lvfs.models import Firmware, Component, Protocol

    plugin = Plugin('uefi-extract')
    for _argv in sys.argv[1:]:
        print('Processing', _argv)
        _test = Test(plugin_id=plugin.id)
        _fw = Firmware()
        _md = Component()
        _md.component_id = 999999
        _md.filename_contents = 'filename.bin'
        _md.protocol = Protocol(value='org.uefi.capsule')
        with open(_argv, 'rb') as _f:
            _md.blob = _f.read()
        _fw.mds.append(_md)
        for _md in _fw.mds:
            plugin.run_test_on_md(_test, _md)
        for attribute in _test.attributes:
            print(attribute)
        for _shard in _md.shards:
            print(_shard.guid, _shard.name, _shard.checksum)
            for _attr in _shard.attributes:
                print(_attr.key, _attr.value)
