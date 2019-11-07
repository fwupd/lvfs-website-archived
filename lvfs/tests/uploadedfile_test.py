#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2018 Richard Hughes <richard@hughsie.com>
#
# SPDX-License-Identifier: GPL-2.0+
#
# pylint: disable=no-self-use,protected-access,wrong-import-position,too-many-public-methods

import os
import sys
import unittest
import zipfile
import io

# allows us to run this from the project root
sys.path.append(os.path.realpath('.'))

from lvfs.uploadedfile import UploadedFile, FileTooSmall, FileNotSupported, MetadataInvalid
from lvfs.util import _validate_guid
from lvfs.models import Verfmt

from cabarchive import CabArchive, CabFile

def _get_valid_firmware():
    return CabFile('fubar'.ljust(1024).encode('utf-8'))

def _get_valid_metainfo(release_description='This stable release fixes bugs',
                        version_format='quad', enable_inf_parsing=True):
    txt = """<?xml version="1.0" encoding="UTF-8"?>
<!-- Copyright 2015 Richard Hughes <richard@hughsie.com> -->
<component type="firmware">
  <id>com.hughski.ColorHug.firmware</id>
  <name>ColorHug</name>
  <name_variant_suffix>China</name_variant_suffix>
  <summary>Firmware for the ColorHug</summary>
  <description><p>Updating the firmware improves performance.</p></description>
  <provides>
    <firmware type="flashed">84f40464-9272-4ef7-9399-cd95f12da696</firmware>
  </provides>
  <url type="homepage">http://www.hughski.com/</url>
  <metadata_license>CC0-1.0</metadata_license>
  <project_license>GPL-2.0+</project_license>
  <developer_name>Hughski Limited</developer_name>
  <releases>
    <release version="0x30002" timestamp="1424116753">
      <description><p>%s</p></description>
    </release>
  </releases>
  <custom>
    <value key="foo">bar</value>
    <value key="LVFS::InhibitDownload"/>
    <value key="LVFS::VersionFormat">%s</value>
    <value key="LVFS::EnableInfParsing">%s</value>
  </custom>
</component>
""" % (release_description, version_format, str(enable_inf_parsing).lower())
    return CabFile(txt.encode('utf-8'))

def _get_alternate_metainfo():
    txt = """<?xml version="1.0" encoding="UTF-8"?>
<!-- Copyright 2019 Richard Hughes <richard@hughsie.com> -->
<component type="firmware">
  <id>com.hughski.ColorHug.firmware</id>
  <name>ColorHug</name>
  <summary>Firmware for the ColorHug</summary>
  <description><p>Updating the firmware improves performance.</p></description>
  <provides>
    <firmware type="flashed">84f40464-9272-4ef7-9399-cd95f12da696</firmware>
  </provides>
  <url type="homepage">http://www.hughski.com/</url>
  <metadata_license>CC0-1.0</metadata_license>
  <project_license>proprietary</project_license>
  <developer_name>Hughski Limited</developer_name>
  <releases>
    <release version="1.2.3" date="2019-07-02">
      <description><p>This stable release fixes bugs</p></description>
    </release>
  </releases>
</component>
"""
    return CabFile(txt.encode('utf-8'))

def _get_generated_metainfo():
    txt = """<?xml version="1.0" encoding="utf-8"?>
<component type="firmware">
 <id>
  com.dell.tbt7d538854.firmware
 </id>
 <provides>
  <firmware type="flashed">
   7d538854-204d-51b2-8f9d-1fe881c70200
  </firmware>
 </provides>
 <name>
  XPS 7390 Thunderbolt
 </name>
 <summary>
  Update for the Thunderbolt host controller in a XPS 7390
 </summary>
 <description>
  <p>
   Updating the thunderbolt NVM improves performance and stability.
  </p>
 </description>
 <url type="homepage">
  http://support.dell.com/
 </url>
 <metadata_license>
  CC0-1.0
 </metadata_license>
 <project_license>
  proprietary
 </project_license>
 <developer_name>
  Dell Inc.
 </developer_name>
 <requires>
  <id compare="ge" version="1.2.3">org.freedesktop.fwupd</id>
  <hardware>
   foo|bar|baz
  </hardware>
  <firmware compare="ge" version="0.2.3"/>
  <firmware compare="eq" version="0.0.1">
   bootloader
  </firmware>
 </requires>
 <keywords>
  <keyword>
   thunderbolt
  </keyword>
 </keywords>
 <releases>
  <release timestamp="1561009099" version="41.01">
   <checksum filename="0x0962_nonsecure.bin" target="content"/>
  </release>
 </releases>
</component>
"""
    return CabFile(txt.encode('utf-8'))

def _get_valid_inf():
    txt = """[Version]
Class=Firmware
ClassGuid={f2e7dd72-6468-4e36-b6f1-6488f42c1b52}
DriverVer=04/18/2015,2.0.3

[Firmware_CopyFiles]
firmware.bin

[Firmware_AddReg]
HKR,,FirmwareId,,{2082b5e0-7a64-478a-b1b2-e3404fab6dad}
HKR,,FirmwareVersion,%REG_DWORD%,0x0000000
HKR,,FirmwareFilename,,firmware.bin

[Strings]
Provider     = "Hughski"
MfgName      = "Hughski Limited"
FirmwareDesc = "ColorHug2 Firmware"
DiskName     = "Firmware for the ColorHug2 Colorimeter"
"""
    return CabFile(txt.encode('utf-8'))

def _add_version_formats(ufile):
    for verfmt in [Verfmt(value='triplet'),
                   Verfmt(value='quad')]:
        ufile.version_formats[verfmt.value] = verfmt

class InMemoryZip:
    def __init__(self):
        self.in_memory_zip = io.BytesIO()

    def __del__(self):
        self.in_memory_zip.close()

    def append(self, filename_in_zip, file_contents):
        zf = zipfile.ZipFile(self.in_memory_zip, "a", zipfile.ZIP_STORED, False)
        zf.writestr(filename_in_zip, file_contents)
        for zfile in zf.filelist:
            zfile.create_system = 0
        return self

    def read(self):
        self.in_memory_zip.seek(0)
        return self.in_memory_zip.read()

class TestStringMethods(unittest.TestCase):

    def test_validate_guid(self):
        self.assertTrue(_validate_guid('84f40464-9272-4ef7-9399-cd95f12da696'))
        self.assertFalse(_validate_guid(None))
        self.assertFalse(_validate_guid(''))
        self.assertFalse(_validate_guid('hello dave'))
        self.assertFalse(_validate_guid('84F40464-9272-4EF7-9399-CD95F12DA696'))
        self.assertFalse(_validate_guid('84f40464-9272-4ef7-9399'))
        self.assertFalse(_validate_guid('84f40464-9272-4ef7-xxxx-cd95f12da696'))

    def test_src_empty(self):
        with self.assertRaises(FileTooSmall):
            ufile = UploadedFile()
            _add_version_formats(ufile)
            ufile.parse('foo.cab', '')
        self.assertEqual(ufile.fwupd_min_version, '0.8.0')

    # no metainfo.xml
    def test_metainfo_missing(self):
        cabarchive = CabArchive()
        cabarchive['firmware.bin'] = _get_valid_firmware()
        with self.assertRaises(MetadataInvalid):
            ufile = UploadedFile()
            _add_version_formats(ufile)
            ufile.parse('foo.cab', cabarchive.save())

    # trying to upload the wrong type
    def test_invalid_type(self):
        cabarchive = CabArchive()
        cabarchive['firmware.bin'] = _get_valid_firmware()
        with self.assertRaises(FileNotSupported):
            ufile = UploadedFile()
            _add_version_formats(ufile)
            ufile.parse('foo.doc', cabarchive.save())

    # invalid metainfo
    def test_metainfo_invalid(self):
        cabarchive = CabArchive()
        cabarchive['firmware.bin'] = _get_valid_firmware()
        cabarchive['firmware.metainfo.xml'] = CabFile(b'<compoXXXXnent/>')
        with self.assertRaises(MetadataInvalid):
            ufile = UploadedFile()
            _add_version_formats(ufile)
            ufile.parse('foo.cab', cabarchive.save())

    # invalid .inf file
    def test_inf_invalid(self):
        cabarchive = CabArchive()
        cabarchive['firmware.bin'] = _get_valid_firmware()
        cabarchive['firmware.metainfo.xml'] = CabFile(b'<component/>')
        cabarchive['firmware.inf'] = CabFile(b'fubar')
        with self.assertRaises(MetadataInvalid):
            ufile = UploadedFile()
            _add_version_formats(ufile)
            ufile.parse('foo.cab', cabarchive.save())

    # archive .cab with firmware.bin of the wrong name
    def test_missing_firmware(self):
        cabarchive = CabArchive()
        cabarchive['firmware123.bin'] = _get_valid_firmware()
        cabarchive['firmware.metainfo.xml'] = _get_valid_metainfo()
        with self.assertRaises(MetadataInvalid):
            ufile = UploadedFile()
            _add_version_formats(ufile)
            ufile.parse('foo.cab', cabarchive.save())

    # valid firmware
    def test_valid(self):
        cabarchive = CabArchive()
        cabarchive['firmware.bin'] = _get_valid_firmware()
        cabarchive['firmware.metainfo.xml'] = _get_valid_metainfo()
        ufile = UploadedFile()
        _add_version_formats(ufile)
        ufile.parse('foo.cab', cabarchive.save())
        cabarchive2 = ufile.cabarchive_repacked
        self.assertIsNotNone(cabarchive2['firmware.bin'])
        self.assertIsNotNone(cabarchive2['firmware.metainfo.xml'])

    # valid firmware with inf file
    def test_valid_with_inf(self):
        cabarchive = CabArchive()
        cabarchive['firmware.bin'] = _get_valid_firmware()
        cabarchive['firmware.metainfo.xml'] = _get_valid_metainfo()
        cabarchive['firmware.inf'] = _get_valid_inf()
        ufile = UploadedFile()
        _add_version_formats(ufile)
        ufile.parse('foo.cab', cabarchive.save())
        cabarchive2 = ufile.cabarchive_repacked
        self.assertIsNotNone(cabarchive2['firmware.bin'])
        self.assertIsNotNone(cabarchive2['firmware.metainfo.xml'])
        self.assertIsNotNone(cabarchive2['firmware.inf'])

    # valid firmware with ignored inf file
    def test_valid_with_ignored_inf(self):
        cabarchive = CabArchive()
        cabarchive['firmware.bin'] = _get_valid_firmware()
        cabarchive['firmware.metainfo.xml'] = _get_valid_metainfo(enable_inf_parsing=False)
        cabarchive['firmware.inf'] = CabFile(b'fubar')
        ufile = UploadedFile()
        _add_version_formats(ufile)
        ufile.parse('foo.cab', cabarchive.save())
        cabarchive2 = ufile.cabarchive_repacked
        self.assertIsNotNone(cabarchive2['firmware.bin'])
        self.assertIsNotNone(cabarchive2['firmware.metainfo.xml'])
        self.assertIsNotNone(cabarchive2['firmware.inf'])

    # invalid version-format
    def test_invalid_version_format(self):
        cabarchive = CabArchive()
        cabarchive['firmware.bin'] = _get_valid_firmware()
        cabarchive['firmware.metainfo.xml'] = _get_valid_metainfo(version_format='foo')
        with self.assertRaises(MetadataInvalid):
            ufile = UploadedFile()
            _add_version_formats(ufile)
            ufile.parse('foo.cab', cabarchive.save())

    # invalid XML header
    def test_invalid_xml_header(self):
        cabarchive = CabArchive()
        cabarchive['firmware.bin'] = _get_valid_firmware()
        cabarchive['firmware.metainfo.xml'] = CabFile(b'<!-- Copyright 2015 Richard Hughes <richard@hughsie.com> -->\n'
                                                      b'<?xml version="1.0" encoding="UTF-8"?>\n'
                                                      b'<component type="firmware"/>\n')
        with self.assertRaises(MetadataInvalid):
            ufile = UploadedFile()
            _add_version_formats(ufile)
            ufile.parse('foo.cab', cabarchive.save())

    # invalid BOM header
    def test_invalid_bom(self):
        cabarchive = CabArchive()
        cabarchive['firmware.bin'] = _get_valid_firmware()
        cabarchive['firmware.metainfo.xml'] = CabFile(b'\xEF\xBB\xBF<?xml version="1.0" encoding="UTF-8"?>\n'
                                                      b'<component type="firmware"/>\n')
        with self.assertRaises(MetadataInvalid):
            ufile = UploadedFile()
            _add_version_formats(ufile)
            ufile.parse('foo.cab', cabarchive.save())

    # valid metadata
    def test_metadata(self):
        cabarchive = CabArchive()
        cabarchive['firmware.bin'] = _get_valid_firmware()
        cabarchive['firmware.metainfo.xml'] = _get_valid_metainfo()
        ufile = UploadedFile()
        _add_version_formats(ufile)
        ufile.parse('foo.cab', cabarchive.save())
        self.assertTrue(ufile.fw.mds[0].inhibit_download)
        self.assertTrue(ufile.fw.mds[0].verfmt.value == 'quad')

    # valid metadata
    def test_release_date(self):
        cabarchive = CabArchive()
        cabarchive['firmware.bin'] = _get_valid_firmware()
        cabarchive['firmware.metainfo.xml'] = _get_alternate_metainfo()
        ufile = UploadedFile()
        _add_version_formats(ufile)
        ufile.parse('foo.cab', cabarchive.save())
        self.assertEqual(ufile.fw.mds[0].release_timestamp, 1562025600)

    # update description references another file
    def test_release_mentions_file(self):
        cabarchive = CabArchive()
        cabarchive['firmware.bin'] = _get_valid_firmware()
        cabarchive['README.txt'] = _get_valid_firmware()
        cabarchive['firmware.metainfo.xml'] = \
            _get_valid_metainfo(release_description='See README.txt for details.')
        with self.assertRaises(MetadataInvalid):
            ufile = UploadedFile()
            _add_version_formats(ufile)
            ufile.parse('foo.cab', cabarchive.save())

    # archive .cab with path with forward-slashes
    def test_valid_path(self):
        cabarchive = CabArchive()
        cabarchive['DriverPackage/firmware.bin'] = _get_valid_firmware()
        cabarchive['DriverPackage/firmware.metainfo.xml'] = _get_valid_metainfo()
        ufile = UploadedFile()
        _add_version_formats(ufile)
        ufile.parse('foo.cab', cabarchive.save())
        cabarchive2 = ufile.cabarchive_repacked
        self.assertIsNotNone(cabarchive2['firmware.bin'])
        self.assertIsNotNone(cabarchive2['firmware.metainfo.xml'])

    # archive .cab with path with backslashes
    def test_valid_path_back(self):
        cabarchive = CabArchive()
        cabarchive['DriverPackage\\firmware.bin'] = _get_valid_firmware()
        cabarchive['DriverPackage\\firmware.metainfo.xml'] = _get_valid_metainfo()
        ufile = UploadedFile()
        _add_version_formats(ufile)
        ufile.parse('foo.cab', cabarchive.save())
        cabarchive2 = ufile.cabarchive_repacked
        self.assertIsNotNone(cabarchive2['firmware.bin'])
        self.assertIsNotNone(cabarchive2['firmware.metainfo.xml'])

    # archive with extra files
    def test_extra_files(self):
        cabarchive = CabArchive()
        cabarchive['firmware.bin'] = _get_valid_firmware()
        cabarchive['firmware.metainfo.xml'] = _get_valid_metainfo()
        cabarchive['README.txt'] = CabFile(b'fubar')
        ufile = UploadedFile()
        _add_version_formats(ufile)
        ufile.parse('foo.cab', cabarchive.save())
        cabarchive2 = ufile.cabarchive_repacked
        self.assertIsNotNone(cabarchive2['firmware.bin'])
        self.assertIsNotNone(cabarchive2['firmware.metainfo.xml'])
        with self.assertRaises(KeyError):
            self.assertIsNotNone(cabarchive2['README.txt'])

    # archive with multiple metainfo files pointing to the same firmware
    def test_multiple_metainfo_same_firmware(self):
        cabarchive = CabArchive()
        cabarchive['firmware.bin'] = _get_valid_firmware()
        cabarchive['firmware1.metainfo.xml'] = _get_valid_metainfo()
        cabarchive['firmware2.metainfo.xml'] = _get_valid_metainfo()

        ufile = UploadedFile()
        _add_version_formats(ufile)
        ufile.parse('foo.cab', cabarchive.save())
        cabarchive2 = ufile.cabarchive_repacked
        self.assertIsNotNone(cabarchive2['firmware.bin'])
        self.assertIsNotNone(cabarchive2['firmware1.metainfo.xml'])
        self.assertIsNotNone(cabarchive2['firmware2.metainfo.xml'])

    # autogenerated archive
    def test_autogenerated(self):
        cabarchive = CabArchive()
        cabarchive['0x0962_nonsecure.bin'] = _get_valid_firmware()
        cabarchive['NVM0.metainfo.xml'] = _get_generated_metainfo()
        ufile = UploadedFile()
        _add_version_formats(ufile)
        ufile.parse('foo.cab', cabarchive.save())

    # windows .zip with path with backslashes
    def test_valid_zipfile(self):
        imz = InMemoryZip()
        imz.append('DriverPackage\\firmware.bin', _get_valid_firmware().buf)
        imz.append('DriverPackage\\firmware.metainfo.xml', _get_valid_metainfo().buf)
        ufile = UploadedFile()
        _add_version_formats(ufile)
        ufile.parse('foo.zip', imz.read())
        cabarchive2 = ufile.cabarchive_repacked
        self.assertIsNotNone(cabarchive2['firmware.bin'])
        self.assertIsNotNone(cabarchive2['firmware.metainfo.xml'])

if __name__ == '__main__':
    unittest.main()
