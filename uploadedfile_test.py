#!/usr/bin/python2
# -*- coding: utf-8 -*-
#
# Copyright (C) 2018 Richard Hughes <richard@hughsie.com>
# Licensed under the GNU General Public License Version 2
#
# pylint: disable=no-self-use,protected-access

import unittest
import zipfile
import StringIO

from gi.repository import GCab
from gi.repository import Gio

from app.uploadedfile import UploadedFile, FileTooSmall, FileNotSupported, MetadataInvalid
from app.util import _archive_get_files_from_glob, _archive_add, _get_basename_safe
from app.pluginloader import Pluginloader, PluginBase

def _get_valid_firmware():
    return 'fubar'.ljust(1024)

def _get_valid_metainfo(release_description='This stable release fixes bugs'):
    return """
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
    <release version="3.0.2" timestamp="1424116753">
      <description><p>%s</p></description>
    </release>
  </releases>
  <custom>
    <value key="foo">bar</value>
    <value key="LVFS::InhibitDownload"/>
  </custom>
</component>
""" % release_description

def _archive_to_contents(arc):
    ostream = Gio.MemoryOutputStream.new_resizable()
    arc.write_simple(ostream)
    return Gio.MemoryOutputStream.steal_as_bytes(ostream).get_data()

class InMemoryZip(object):
    def __init__(self):
        self.in_memory_zip = StringIO.StringIO()

    def append(self, filename_in_zip, file_contents):
        zf = zipfile.ZipFile(self.in_memory_zip, "a", zipfile.ZIP_STORED, False)
        zf.writestr(filename_in_zip, file_contents)
        for zfile in zf.filelist:
            zfile.create_system = 0
        return self

    def read(self):
        self.in_memory_zip.seek(0)
        return self.in_memory_zip.read()

class TestPlugin(PluginBase):

    def __init__(self):
        PluginBase.__init__(self, 'test')

    def archive_sign(self, arc, firmware_cff):
        detached_fn = _get_basename_safe(firmware_cff.get_name() + '.asc')
        if _archive_get_files_from_glob(arc, detached_fn):
            return
        _archive_add(arc, detached_fn, 'signed')

class TestStringMethods(unittest.TestCase):

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
        _archive_add(arc, 'firmware.metainfo.xml', '<compoXXXXnent/>')
        with self.assertRaises(MetadataInvalid):
            ufile = UploadedFile()
            ufile.parse('foo.cab', _archive_to_contents(arc))

    # invalid .inf file
    def test_inf_invalid(self):
        arc = GCab.Cabinet.new()
        _archive_add(arc, 'firmware.bin', _get_valid_firmware())
        _archive_add(arc, 'firmware.metainfo.xml', '<component/>')
        _archive_add(arc, 'firmware.inf', 'fubar')
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

    # valid metadata
    def test_metadata(self):
        arc = GCab.Cabinet.new()
        _archive_add(arc, 'firmware.bin', _get_valid_firmware())
        _archive_add(arc, 'firmware.metainfo.xml', _get_valid_metainfo())
        ufile = UploadedFile()
        ufile.parse('foo.cab', _archive_to_contents(arc))
        self.assertTrue('foo' in ufile.metadata)
        self.assertTrue('LVFS::InhibitDownload' in ufile.metadata)
        self.assertTrue(ufile.metadata['foo'] == 'bar')
        self.assertFalse('NotGoingToExist' in ufile.metadata)

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
        _archive_add(arc, 'README.txt', 'fubar')
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

        # use a fake plugin to add a file
        ploader = Pluginloader()
        ploader.loaded = True
        ploader._plugins = [TestPlugin()]

        ufile = UploadedFile(ploader)
        ufile.parse('foo.cab', _archive_to_contents(arc))
        arc2 = ufile.get_repacked_cabinet()
        self.assertTrue(_archive_get_files_from_glob(arc2, 'firmware.bin'))
        self.assertTrue(_archive_get_files_from_glob(arc2, 'firmware.bin.asc'))
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
