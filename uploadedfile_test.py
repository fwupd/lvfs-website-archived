#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2018 Richard Hughes <richard@hughsie.com>
# Licensed under the GNU General Public License Version 2
#
# pylint: disable=no-self-use,protected-access,wrong-import-position

import unittest
import zipfile
import io
import gi

gi.require_version('GCab', '1.0')

from gi.repository import GCab
from gi.repository import Gio

from app.uploadedfile import UploadedFile, FileTooSmall, FileNotSupported, MetadataInvalid
from app.util import _archive_get_files_from_glob, _archive_add, _validate_guid

def _get_valid_firmware():
    return 'fubar'.ljust(1024).encode('utf-8')

def _get_valid_metainfo(release_description='This stable release fixes bugs',
                        version_format='quad'):
    txt = """
<?xml version="1.0" encoding="UTF-8"?>
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
    return txt.encode('utf-8')

def _archive_to_contents(arc):
    ostream = Gio.MemoryOutputStream.new_resizable()
    arc.write_simple(ostream)
    return Gio.MemoryOutputStream.steal_as_bytes(ostream).get_data()

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
        arc = GCab.Cabinet.new()
        _archive_add(arc, 'firmware.bin', _get_valid_firmware())
        with self.assertRaises(MetadataInvalid):
            ufile = UploadedFile()
            ufile.parse('foo.cab', _archive_to_contents(arc))

    # trying to upload the wrong type
    def test_invalid_type(self):
        arc = GCab.Cabinet.new()
        _archive_add(arc, 'firmware.bin', _get_valid_firmware())
        with self.assertRaises(FileNotSupported):
            ufile = UploadedFile()
            ufile.parse('foo.doc', _archive_to_contents(arc))

    # invalid metainfo
    def test_metainfo_invalid(self):
        arc = GCab.Cabinet.new()
        _archive_add(arc, 'firmware.bin', _get_valid_firmware())
        _archive_add(arc, 'firmware.metainfo.xml', b'<compoXXXXnent/>')
        with self.assertRaises(MetadataInvalid):
            ufile = UploadedFile()
            ufile.parse('foo.cab', _archive_to_contents(arc))

    # invalid .inf file
    def test_inf_invalid(self):
        arc = GCab.Cabinet.new()
        _archive_add(arc, 'firmware.bin', _get_valid_firmware())
        _archive_add(arc, 'firmware.metainfo.xml', b'<component/>')
        _archive_add(arc, 'firmware.inf', b'fubar')
        with self.assertRaises(MetadataInvalid):
            ufile = UploadedFile()
            ufile.parse('foo.cab', _archive_to_contents(arc))

    # archive .cab with firmware.bin of the wrong name
    def test_missing_firmware(self):
        arc = GCab.Cabinet.new()
        _archive_add(arc, 'firmware123.bin', _get_valid_firmware())
        _archive_add(arc, 'firmware.metainfo.xml', _get_valid_metainfo())
        with self.assertRaises(MetadataInvalid):
            ufile = UploadedFile()
            ufile.parse('foo.cab', _archive_to_contents(arc))

    # valid firmware
    def test_valid(self):
        arc = GCab.Cabinet.new()
        _archive_add(arc, 'firmware.bin', _get_valid_firmware())
        _archive_add(arc, 'firmware.metainfo.xml', _get_valid_metainfo())
        ufile = UploadedFile()
        ufile.parse('foo.cab', _archive_to_contents(arc))
        arc2 = ufile.get_repacked_cabinet()
        self.assertIsNotNone(_archive_get_files_from_glob(arc2, 'firmware.bin'))
        self.assertIsNotNone(_archive_get_files_from_glob(arc2, 'firmware.metainfo.xml'))

    # invalid version-format
    def test_invalid_version_format(self):
        arc = GCab.Cabinet.new()
        _archive_add(arc, 'firmware.bin', _get_valid_firmware())
        _archive_add(arc, 'firmware.metainfo.xml', _get_valid_metainfo(version_format='foo'))
        with self.assertRaises(MetadataInvalid):
            ufile = UploadedFile()
            ufile.parse('foo.cab', _archive_to_contents(arc))

    # valid metadata
    def test_metadata(self):
        arc = GCab.Cabinet.new()
        _archive_add(arc, 'firmware.bin', _get_valid_firmware())
        _archive_add(arc, 'firmware.metainfo.xml', _get_valid_metainfo())
        ufile = UploadedFile()
        ufile.parse('foo.cab', _archive_to_contents(arc))
        metadata = ufile.get_components()[0].get_metadata()
        self.assertTrue('foo' in metadata)
        self.assertTrue('LVFS::InhibitDownload' in metadata)
        self.assertTrue(metadata['foo'] == 'bar')
        self.assertTrue('LVFS::VersionFormat' in metadata)
        self.assertTrue(metadata['LVFS::VersionFormat'] == 'quad')
        self.assertFalse('NotGoingToExist' in metadata)

    # update description references another file
    def test_release_mentions_file(self):
        arc = GCab.Cabinet.new()
        _archive_add(arc, 'firmware.bin', _get_valid_firmware())
        _archive_add(arc, 'README.txt', _get_valid_firmware())
        _archive_add(arc, 'firmware.metainfo.xml',
                     _get_valid_metainfo(release_description='See README.txt for details.'))
        with self.assertRaises(MetadataInvalid):
            ufile = UploadedFile()
            ufile.parse('foo.cab', _archive_to_contents(arc))

    # archive .cab with path with forward-slashes
    def test_valid_path(self):
        arc = GCab.Cabinet.new()
        _archive_add(arc, 'DriverPackage/firmware.bin', _get_valid_firmware())
        _archive_add(arc, 'DriverPackage/firmware.metainfo.xml', _get_valid_metainfo())
        ufile = UploadedFile()
        ufile.parse('foo.cab', _archive_to_contents(arc))
        arc2 = ufile.get_repacked_cabinet()
        self.assertTrue(_archive_get_files_from_glob(arc2, 'firmware.bin'))
        self.assertTrue(_archive_get_files_from_glob(arc2, 'firmware.metainfo.xml'))

    # archive .cab with path with backslashes
    def test_valid_path_back(self):
        arc = GCab.Cabinet.new()
        _archive_add(arc, 'DriverPackage\\firmware.bin', _get_valid_firmware())
        _archive_add(arc, 'DriverPackage\\firmware.metainfo.xml', _get_valid_metainfo())
        ufile = UploadedFile()
        ufile.parse('foo.cab', _archive_to_contents(arc))
        arc2 = ufile.get_repacked_cabinet()
        self.assertTrue(_archive_get_files_from_glob(arc2, 'firmware.bin'))
        self.assertTrue(_archive_get_files_from_glob(arc2, 'firmware.metainfo.xml'))

    # archive with extra files
    def test_extra_files(self):
        arc = GCab.Cabinet.new()
        _archive_add(arc, 'firmware.bin', _get_valid_firmware())
        _archive_add(arc, 'firmware.metainfo.xml', _get_valid_metainfo())
        _archive_add(arc, 'README.txt', b'fubar')
        ufile = UploadedFile()
        ufile.parse('foo.cab', _archive_to_contents(arc))
        arc2 = ufile.get_repacked_cabinet()
        self.assertTrue(_archive_get_files_from_glob(arc2, 'firmware.bin'))
        self.assertTrue(_archive_get_files_from_glob(arc2, 'firmware.metainfo.xml'))
        self.assertFalse(_archive_get_files_from_glob(arc2, 'README.txt'))

    # archive with multiple metainfo files pointing to the same firmware
    def test_multiple_metainfo_same_firmware(self):
        arc = GCab.Cabinet.new()
        _archive_add(arc, 'firmware.bin', _get_valid_firmware())
        _archive_add(arc, 'firmware1.metainfo.xml', _get_valid_metainfo())
        _archive_add(arc, 'firmware2.metainfo.xml', _get_valid_metainfo())

        ufile = UploadedFile()
        ufile.parse('foo.cab', _archive_to_contents(arc))
        arc2 = ufile.get_repacked_cabinet()
        self.assertTrue(_archive_get_files_from_glob(arc2, 'firmware.bin'))
        self.assertTrue(_archive_get_files_from_glob(arc2, 'firmware1.metainfo.xml'))
        self.assertTrue(_archive_get_files_from_glob(arc2, 'firmware2.metainfo.xml'))

    # windows .zip with path with backslashes
    def test_valid_zipfile(self):
        imz = InMemoryZip()
        imz.append('DriverPackage\\firmware.bin', _get_valid_firmware())
        imz.append('DriverPackage\\firmware.metainfo.xml', _get_valid_metainfo())
        ufile = UploadedFile()
        ufile.parse('foo.zip', imz.read())
        arc2 = ufile.get_repacked_cabinet()
        self.assertTrue(_archive_get_files_from_glob(arc2, 'firmware.bin'))
        self.assertTrue(_archive_get_files_from_glob(arc2, 'firmware.metainfo.xml'))

if __name__ == '__main__':
    unittest.main()
