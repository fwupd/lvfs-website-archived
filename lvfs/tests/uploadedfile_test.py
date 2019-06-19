#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2018 Richard Hughes <richard@hughsie.com>
#
# SPDX-License-Identifier: GPL-2.0+
#
# pylint: disable=no-self-use,protected-access,wrong-import-position

import os
import sys
import unittest
import zipfile
import io

# allows us to run this from the project root
sys.path.append(os.path.realpath('.'))

from lvfs.uploadedfile import UploadedFile, FileTooSmall, FileNotSupported, MetadataInvalid
from lvfs.util import _validate_guid

from cabarchive import CabArchive, CabFile

def _get_valid_firmware():
    return CabFile('fubar'.ljust(1024).encode('utf-8'))

def _get_valid_metainfo(release_description='This stable release fixes bugs',
                        version_format='quad'):
    txt = """<?xml version="1.0" encoding="UTF-8"?>
<!-- Copyright 2015 Richard Hughes <richard@hughsie.com> -->
<component type="firmware">
  <id>com.hughski.ColorHug.firmware</id>
  <name>ColorHug Firmware</name>
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
  </custom>
</component>
""" % (release_description, version_format)
    return CabFile(txt.encode('utf-8'))

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
            ufile.parse('foo.cab', '')
        self.assertEqual(ufile.fwupd_min_version, '0.8.0')

    # no metainfo.xml
    def test_metainfo_missing(self):
        cabarchive = CabArchive()
        cabarchive['firmware.bin'] = _get_valid_firmware()
        with self.assertRaises(MetadataInvalid):
            ufile = UploadedFile()
            ufile.parse('foo.cab', cabarchive.save())

    # trying to upload the wrong type
    def test_invalid_type(self):
        cabarchive = CabArchive()
        cabarchive['firmware.bin'] = _get_valid_firmware()
        with self.assertRaises(FileNotSupported):
            ufile = UploadedFile()
            ufile.parse('foo.doc', cabarchive.save())

    # invalid metainfo
    def test_metainfo_invalid(self):
        cabarchive = CabArchive()
        cabarchive['firmware.bin'] = _get_valid_firmware()
        cabarchive['firmware.metainfo.xml'] = CabFile(b'<compoXXXXnent/>')
        with self.assertRaises(MetadataInvalid):
            ufile = UploadedFile()
            ufile.parse('foo.cab', cabarchive.save())

    # invalid .inf file
    def test_inf_invalid(self):
        cabarchive = CabArchive()
        cabarchive['firmware.bin'] = _get_valid_firmware()
        cabarchive['firmware.metainfo.xml'] = CabFile(b'<component/>')
        cabarchive['firmware.inf'] = CabFile(b'fubar')
        with self.assertRaises(MetadataInvalid):
            ufile = UploadedFile()
            ufile.parse('foo.cab', cabarchive.save())

    # archive .cab with firmware.bin of the wrong name
    def test_missing_firmware(self):
        cabarchive = CabArchive()
        cabarchive['firmware123.bin'] = _get_valid_firmware()
        cabarchive['firmware.metainfo.xml'] = _get_valid_metainfo()
        with self.assertRaises(MetadataInvalid):
            ufile = UploadedFile()
            ufile.parse('foo.cab', cabarchive.save())

    # valid firmware
    def test_valid(self):
        cabarchive = CabArchive()
        cabarchive['firmware.bin'] = _get_valid_firmware()
        cabarchive['firmware.metainfo.xml'] = _get_valid_metainfo()
        ufile = UploadedFile()
        ufile.parse('foo.cab', cabarchive.save())
        cabarchive2 = ufile.cabarchive_repacked
        self.assertIsNotNone(cabarchive2['firmware.bin'])
        self.assertIsNotNone(cabarchive2['firmware.metainfo.xml'])

    # invalid version-format
    def test_invalid_version_format(self):
        cabarchive = CabArchive()
        cabarchive['firmware.bin'] = _get_valid_firmware()
        cabarchive['firmware.metainfo.xml'] = _get_valid_metainfo(version_format='foo')
        with self.assertRaises(MetadataInvalid):
            ufile = UploadedFile()
            ufile.parse('foo.cab', cabarchive.save())

    # valid metadata
    def test_metadata(self):
        cabarchive = CabArchive()
        cabarchive['firmware.bin'] = _get_valid_firmware()
        cabarchive['firmware.metainfo.xml'] = _get_valid_metainfo()
        ufile = UploadedFile()
        ufile.parse('foo.cab', cabarchive.save())
        self.assertTrue(ufile.fw.mds[0].inhibit_download)
        self.assertTrue(ufile.fw.mds[0].version_format == 'quad')

    # update description references another file
    def test_release_mentions_file(self):
        cabarchive = CabArchive()
        cabarchive['firmware.bin'] = _get_valid_firmware()
        cabarchive['README.txt'] = _get_valid_firmware()
        cabarchive['firmware.metainfo.xml'] = \
            _get_valid_metainfo(release_description='See README.txt for details.')
        with self.assertRaises(MetadataInvalid):
            ufile = UploadedFile()
            ufile.parse('foo.cab', cabarchive.save())

    # archive .cab with path with forward-slashes
    def test_valid_path(self):
        cabarchive = CabArchive()
        cabarchive['DriverPackage/firmware.bin'] = _get_valid_firmware()
        cabarchive['DriverPackage/firmware.metainfo.xml'] = _get_valid_metainfo()
        ufile = UploadedFile()
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
        ufile.parse('foo.cab', cabarchive.save())
        cabarchive2 = ufile.cabarchive_repacked
        self.assertIsNotNone(cabarchive2['firmware.bin'])
        self.assertIsNotNone(cabarchive2['firmware1.metainfo.xml'])
        self.assertIsNotNone(cabarchive2['firmware2.metainfo.xml'])

    # windows .zip with path with backslashes
    def test_valid_zipfile(self):
        imz = InMemoryZip()
        imz.append('DriverPackage\\firmware.bin', _get_valid_firmware().buf)
        imz.append('DriverPackage\\firmware.metainfo.xml', _get_valid_metainfo().buf)
        ufile = UploadedFile()
        ufile.parse('foo.zip', imz.read())
        cabarchive2 = ufile.cabarchive_repacked
        self.assertIsNotNone(cabarchive2['firmware.bin'])
        self.assertIsNotNone(cabarchive2['firmware.metainfo.xml'])

if __name__ == '__main__':
    unittest.main()
