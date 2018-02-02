#!/usr/bin/python2
# -*- coding: utf-8 -*-
#
# Copyright (C) 2018 Richard Hughes <richard@hughsie.com>
# Licensed under the GNU General Public License Version 2

import unittest
import zipfile
import StringIO

from gi.repository import GCab
from gi.repository import Gio
from gi.repository import GLib

from app.uploadedfile import UploadedFile, FileTooSmall, FileNotSupported, MetadataInvalid
from app.util import _archive_get_files_from_glob

def _archive_create():
    arc = GCab.Cabinet.new()
    cffolder = GCab.Folder.new(GCab.Compression.NONE)
    arc.add_folder(cffolder)
    return arc

def _archive_add(arc, filename, contents):
    cffile = GCab.File.new_with_bytes(filename, GLib.Bytes.new(contents))
    cffolders = arc.get_folders()
    cffolders[0].add_file(cffile, False)

def _get_valid_firmware():
    return 'fubar'.ljust(1024)

def _get_valid_metainfo():
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
      <description><p>This stable release fixes bugs</p></description>
    </release>
  </releases>
</component>
"""

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

class TestStringMethods(unittest.TestCase):

    def test_src_empty(self):
        with self.assertRaises(FileTooSmall):
            ufile = UploadedFile()
            ufile.parse('foo.cab', '')
        self.assertEqual(ufile.fwupd_min_version, '0.8.0')

    # no metainfo.xml
    def test_metainfo_missing(self):
        arc = _archive_create()
        _archive_add(arc, 'firmware.bin', _get_valid_firmware())
        with self.assertRaises(MetadataInvalid):
            ufile = UploadedFile()
            ufile.parse('foo.cab', _archive_to_contents(arc))

    # trying to upload the wrong type
    def test_invalid_type(self):
        arc = _archive_create()
        _archive_add(arc, 'firmware.bin', _get_valid_firmware())
        with self.assertRaises(FileNotSupported):
            ufile = UploadedFile()
            ufile.parse('foo.doc', _archive_to_contents(arc))

    # invalid metainfo
    def test_metainfo_invalid(self):
        arc = _archive_create()
        _archive_add(arc, 'firmware.bin', _get_valid_firmware())
        _archive_add(arc, 'firmware.metainfo.xml', '<compoXXXXnent/>')
        with self.assertRaises(MetadataInvalid):
            ufile = UploadedFile()
            ufile.parse('foo.cab', _archive_to_contents(arc))

    # invalid .inf file
    def test_inf_invalid(self):
        arc = _archive_create()
        _archive_add(arc, 'firmware.bin', _get_valid_firmware())
        _archive_add(arc, 'firmware.metainfo.xml', '<component/>')
        _archive_add(arc, 'firmware.inf', 'fubar')
        with self.assertRaises(MetadataInvalid):
            ufile = UploadedFile()
            ufile.parse('foo.cab', _archive_to_contents(arc))

    # archive .cab with firmware.bin of the wrong name
    def test_missing_firmware(self):
        arc = _archive_create()
        _archive_add(arc, 'firmware123.bin', _get_valid_firmware())
        _archive_add(arc, 'firmware.metainfo.xml', _get_valid_metainfo())
        with self.assertRaises(MetadataInvalid):
            ufile = UploadedFile()
            ufile.parse('foo.cab', _archive_to_contents(arc))

    # valid firmware
    def test_valid(self):
        arc = _archive_create()
        _archive_add(arc, 'firmware.bin', _get_valid_firmware())
        _archive_add(arc, 'firmware.metainfo.xml', _get_valid_metainfo())
        ufile = UploadedFile()
        ufile.parse('foo.cab', _archive_to_contents(arc))
        arc2 = ufile.get_repacked_cabinet()
        self.assertIsNotNone(_archive_get_files_from_glob(arc2, 'firmware.bin'))
        self.assertIsNotNone(_archive_get_files_from_glob(arc2, 'firmware.metainfo.xml'))

    # archive .cab with path with forward-slashes
    def test_valid_path(self):
        arc = _archive_create()
        _archive_add(arc, 'DriverPackage/firmware.bin', _get_valid_firmware())
        _archive_add(arc, 'DriverPackage/firmware.metainfo.xml', _get_valid_metainfo())
        ufile = UploadedFile()
        ufile.parse('foo.cab', _archive_to_contents(arc))
        arc2 = ufile.get_repacked_cabinet()
        self.assertTrue(_archive_get_files_from_glob(arc2, 'firmware.bin'))
        self.assertTrue(_archive_get_files_from_glob(arc2, 'firmware.metainfo.xml'))

    # archive .cab with path with backslashes
    def test_valid_path_back(self):
        arc = _archive_create()
        _archive_add(arc, 'DriverPackage\\firmware.bin', _get_valid_firmware())
        _archive_add(arc, 'DriverPackage\\firmware.metainfo.xml', _get_valid_metainfo())
        ufile = UploadedFile()
        ufile.parse('foo.cab', _archive_to_contents(arc))
        arc2 = ufile.get_repacked_cabinet()
        self.assertTrue(_archive_get_files_from_glob(arc2, 'firmware.bin'))
        self.assertTrue(_archive_get_files_from_glob(arc2, 'firmware.metainfo.xml'))

    # archive with extra files
    def test_extra_files(self):
        arc = _archive_create()
        _archive_add(arc, 'firmware.bin', _get_valid_firmware())
        _archive_add(arc, 'firmware.metainfo.xml', _get_valid_metainfo())
        _archive_add(arc, 'README.txt', 'fubar')
        ufile = UploadedFile()
        ufile.parse('foo.cab', _archive_to_contents(arc))
        arc2 = ufile.get_repacked_cabinet()
        self.assertTrue(_archive_get_files_from_glob(arc2, 'firmware.bin'))
        self.assertTrue(_archive_get_files_from_glob(arc2, 'firmware.metainfo.xml'))
        self.assertFalse(_archive_get_files_from_glob(arc2, 'README.txt'))

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
