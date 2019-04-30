#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2015-2018 Richard Hughes <richard@hughsie.com>
# Licensed under the GNU General Public License Version 2
#
# pylint: disable=fixme,too-many-instance-attributes

import os
import hashlib
import shutil
import subprocess
import tempfile
import configparser

from gi.repository import GCab
from gi.repository import Gio
from gi.repository import GLib
from gi.repository import AppStreamGlib

from .inf_parser import InfParser
from .util import _archive_get_files_from_glob, _get_basename_safe, _validate_guid

class FileTooLarge(Exception):
    pass
class FileTooSmall(Exception):
    pass
class FileNotSupported(Exception):
    pass
class MetadataInvalid(Exception):
    pass

def _listdir_recurse(basedir):
    """ Return all files and folders """
    files = []
    for res in os.listdir(basedir):
        fn = os.path.join(basedir, res)
        if not os.path.isfile(fn):
            children = _listdir_recurse(fn)
            files.extend(children)
            continue
        files.append(fn)
    return files

def _repackage_archive(filename, buf, tmpdir=None):
    """ Unpacks an archive (typically a .zip) into a GCab.Cabinet object """

    # write to temp file
    src = tempfile.NamedTemporaryFile(mode='wb',
                                      prefix='foreignarchive_',
                                      suffix=".cab",
                                      dir=tmpdir,
                                      delete=True)
    src.write(buf)
    src.flush()

    # decompress to a temp directory
    dest_fn = tempfile.mkdtemp(prefix='foreignarchive_', dir=tmpdir)

    # work out what binary to use
    split = filename.rsplit('.', 1)
    if len(split) < 2:
        raise NotImplementedError('Filename not valid')
    if split[1] == 'zip':
        argv = ['/usr/bin/bsdtar', '--directory', dest_fn, '-xvf', src.name]
    else:
        raise NotImplementedError('Filename had no supported extension')

    # bail out early
    if not os.path.exists(argv[0]):
        raise IOError('command %s not found' % argv[0])

    # extract
    ps = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if ps.wait() != 0:
        raise IOError('Failed to extract: %s' % ps.stderr.read())

    # add all the fake CFFILE objects
    arc = GCab.Cabinet.new()
    cffolder = GCab.Folder.new(GCab.Compression.MSZIP)
    arc.add_folder(cffolder)
    for fn in _listdir_recurse(dest_fn):
        with open(fn, 'rb') as f:
            contents = f.read()
        cffile = GCab.File.new_with_bytes(_get_basename_safe(fn),
                                          GLib.Bytes.new(contents))
        cffolder.add_file(cffile, False)
    shutil.rmtree(dest_fn)
    return arc

def detect_encoding_from_bom(b):

    # UTF-8 BOM
    if b[0:3] == b'\xef\xbb\xbf':
        return "utf-8"

    # UTF-16 BOM
    if b[0:2] == b'\xfe\xff' or b[0:2] == b'\xff\xfe':
        return "utf-16"

    # UTF-32 BOM
    if b[0:5] == b'\xfe\xff\x00\x00' or b[0:5] == b'\x00\x00\xff\xfe':
        return "utf-32"

    # fallback
    return "cp1252"

class UploadedFile:

    def __init__(self):
        """ default public attributes """

        self.checksum_upload = None
        self.filename_new = None
        self.fwupd_min_version = '0.8.0'    # a guess, but everyone should have this
        self.version_display = None
        self.version_formats = ['plain', 'pair', 'triplet', 'quad', 'intel-me', 'intel-me2']

        # strip out any unlisted files
        self._repacked_cfarchive = GCab.Cabinet.new()
        self._repacked_cffolder = GCab.Folder.new(GCab.Compression.MSZIP)
        self._repacked_cfarchive.add_folder(self._repacked_cffolder)

        # private
        self._components = []
        self._data_size = 0
        self._source_cfarchive = None
        self._version_inf = None

    def _load_archive(self, filename, data):
        try:
            if filename.endswith('.cab'):
                istream = Gio.MemoryInputStream.new_from_bytes(GLib.Bytes.new(data))
                self._source_cfarchive = GCab.Cabinet.new()
                self._source_cfarchive.load(istream)
                self._source_cfarchive.extract(None)
            else:
                self._source_cfarchive = _repackage_archive(filename, data)
        except NotImplementedError as e:
            raise FileNotSupported('Invalid file type: %s' % str(e))

    def _verify_inf(self, contents):

        # FIXME is banned...
        if contents.find('FIXME') != -1:
            raise MetadataInvalid('The inf file was not complete; Any FIXME text must be '
                                  'replaced with the correct values.')

        # check .inf file is valid
        cfg = InfParser()
        try:
            cfg.read_data(contents)
        except configparser.MissingSectionHeaderError as _:
            raise MetadataInvalid('The inf file could not be parsed')
        try:
            tmp = cfg.get('Version', 'Class')
        except (configparser.NoOptionError, configparser.NoSectionError) as _:
            raise MetadataInvalid('The inf file Version:Class was missing')
        if tmp.lower() != 'firmware':
            raise MetadataInvalid('The inf file Version:Class was invalid')
        try:
            tmp = cfg.get('Version', 'ClassGuid')
        except configparser.NoOptionError as _:
            raise MetadataInvalid('The inf file Version:ClassGuid was missing')
        if tmp.lower() != '{f2e7dd72-6468-4e36-b6f1-6488f42c1b52}':
            raise MetadataInvalid('The inf file Version:ClassGuid was invalid')
        try:
            tmp = cfg.get('Version', 'DriverVer').split(',')
            if len(tmp) != 2:
                raise MetadataInvalid('The inf file Version:DriverVer was invalid')
            self.version_display = tmp[1]
        except configparser.NoOptionError as _:
            pass

        # this is optional, but if supplied must match the version in the XML
        # -- also note this will not work with multi-firmware .cab files
        try:
            self._version_inf = cfg.get('Firmware_AddReg', 'HKR->FirmwareVersion')
            if self._version_inf.startswith('0x'):
                self._version_inf = str(int(self._version_inf[2:], 16))
            if self._version_inf == '0':
                self._version_inf = None
        except (configparser.NoOptionError, configparser.NoSectionError) as _:
            pass

    def _verify_infs(self):

        for cf in _archive_get_files_from_glob(self._source_cfarchive, '*.inf'):
            # accept basically any encoding
            contents_blob = cf.get_bytes().get_data()
            contents = contents_blob.decode(detect_encoding_from_bom(contents_blob))
            self._verify_inf(contents)

    def _add_cf_to_repacked_folder(self, cf):

        # check for duplicate name
        basename = _get_basename_safe(cf.get_name())
        for cffile in self._repacked_cffolder.get_files():
            if basename == cffile.get_name():
                return

        # add file to archive with new safe filename
        cf_safe = GCab.File.new_with_bytes(basename, cf.get_bytes())
        self._repacked_cffolder.add_file(cf_safe, False)

    def _load_metainfo(self, cf):

        component = AppStreamGlib.App.new()
        try:
            # check this is valid UTF-8
            cf.get_bytes().get_data().decode('utf-8')
            component.parse_data(cf.get_bytes(), AppStreamGlib.AppParseFlags.NONE)
            fmt = AppStreamGlib.Format.new()
            fmt.set_kind(AppStreamGlib.FormatKind.METAINFO)
            component.add_format(fmt)
            component.validate(AppStreamGlib.AppValidateFlags.NONE)
        except UnicodeDecodeError as e:
            raise MetadataInvalid('The metadata %s could not be parsed: %s' % (cf.get_name(), str(e)))
        except Exception as e:
            try:
                msg = e.message.decode('utf-8')
            except AttributeError:
                msg = str(e)
            raise MetadataInvalid('The metadata %s could not be parsed: %s' % (cf.get_name(), msg))

        # add to the archive
        self._add_cf_to_repacked_folder(cf)

        # check the file does not have any missing request.form
        contents = cf.get_bytes().get_data()
        if contents.decode('utf-8', 'ignore').find('FIXME') != -1:
            raise MetadataInvalid('The metadata file was not complete; '
                                  'Any FIXME text must be replaced with the correct values.')

        # check the firmware provides something
        if len(component.get_provides()) == 0:
            raise MetadataInvalid('The metadata file did not provide any GUID.')
        for prov in component.get_provides():
            if prov.get_kind() == AppStreamGlib.ProvideKind.FIRMWARE_FLASHED:
                guid = prov.get_value()
                if not _validate_guid(guid):
                    raise MetadataInvalid('The GUID %s was invalid.' % guid)
        release_default = component.get_release_default()
        if not release_default:
            raise MetadataInvalid('The metadata file did not provide any releases.')

        # ensure the update description does not refer to a file in the archive
        release_description = release_default.get_description()
        if release_description:
            for word in release_description.split(' '):
                if word.find('.') == -1: # any word without a dot is not a fn
                    continue
                cfs = _archive_get_files_from_glob(self._source_cfarchive, word)
                if len(cfs):
                    raise MetadataInvalid('The release description should not reference other files.')

        # fix up hex value
        release_version = release_default.get_version()
        if release_version.startswith('0x'):
            release_version = str(int(release_version[2:], 16))
            release_default.set_version(release_version)

        # check the inf file matches up with the .xml file
        if self._version_inf and self._version_inf != release_version:
            raise MetadataInvalid('The inf Firmware_AddReg[HKR->FirmwareVersion] '
                                  '%s did not match the metainfo.xml value %s.'
                                  % (self._version_inf, release_version))

        # check the file didn't try to add it's own <require> on vendor-id
        # to work around the vendor-id security checks in fwupd
        req = component.get_require_by_value(AppStreamGlib.RequireKind.FIRMWARE, 'vendor-id')
        if req:
            raise MetadataInvalid('Firmware cannot specify vendor-id')

        # check only recognised requirements are added
        for req in component.get_requires():
            if req.get_kind() == AppStreamGlib.RequireKind.UNKNOWN:
                raise MetadataInvalid('Requirement \'%s\' was invalid' % req.get_value())

        # check the version format
        version_format = component.get_metadata_item('LVFS::VersionFormat')
        if version_format:
            if version_format not in self.version_formats:
                raise MetadataInvalid('LVFS::VersionFormat can only be %s' % self.version_formats)

        # does the firmware require a specific fwupd version?
        req = component.get_require_by_value(AppStreamGlib.RequireKind.ID,
                                             'org.freedesktop.fwupd')
        if req:
            self.fwupd_min_version = req.get_version()

        # ensure there's always a container checksum
        release = component.get_release_default()
        csum = release.get_checksum_by_target(AppStreamGlib.ChecksumTarget.CONTENT)
        if not csum:
            csum = AppStreamGlib.Checksum.new()
            csum.set_target(AppStreamGlib.ChecksumTarget.CONTENT)
            csum.set_filename('firmware.bin')
            release.add_checksum(csum)

        # get the contents checksum
        cf_name_safe = cf.get_name().replace('\\', '/')
        dirname = os.path.dirname(cf_name_safe)
        firmware_filename = os.path.join(dirname, csum.get_filename())
        cfs = _archive_get_files_from_glob(self._source_cfarchive, firmware_filename)
        if not cfs:
            raise MetadataInvalid('No %s found in the archive' % firmware_filename)

        # add to the archive
        self._add_cf_to_repacked_folder(cfs[0])

        contents = cfs[0].get_bytes().get_data()
        csum.set_kind(GLib.ChecksumType.SHA1)
        csum.set_value(hashlib.sha1(contents).hexdigest())

        # set the sizes
        release.set_size(AppStreamGlib.SizeKind.INSTALLED, len(contents))
        release.set_size(AppStreamGlib.SizeKind.DOWNLOAD, self._data_size)

        # add to array
        self._components.append(component)

    def _load_metainfos(self):

        # check metainfo exists
        cfs = _archive_get_files_from_glob(self._source_cfarchive, '*.metainfo.xml')
        if len(cfs) == 0:
            raise MetadataInvalid('The firmware file had no .metadata.xml files')

        # parse each MetaInfo file
        for cf in cfs:
            self._load_metainfo(cf)

    def parse(self, filename, data, use_hashed_prefix=True):

        # check size
        self._data_size = len(data)
        if self._data_size > 104857600:
            raise FileTooLarge('File too large, limit is 100Mb')
        if self._data_size < 1024:
            raise FileTooSmall('File too small, minimum is 1k')

        # get new filename
        self.checksum_upload = hashlib.sha1(data).hexdigest()
        if use_hashed_prefix:
            self.filename_new = self.checksum_upload + '-' + filename.replace('.zip', '.cab')
        else:
            self.filename_new = filename.replace('.zip', '.cab')

        # parse the file
        self._load_archive(filename, data)

        # verify .inf files if they exists
        self._verify_infs()

        # load metainfo files
        self._load_metainfos()

    def get_components(self):
        """ gets all detected AppStream components """
        return self._components

    def get_source_cabinet(self):
        """ gets the source archive with all files """
        return self._source_cfarchive

    def get_repacked_cabinet(self):
        """ gets the filtered archive with only the defined files """
        return self._repacked_cfarchive
