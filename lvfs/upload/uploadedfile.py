#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2015-2018 Richard Hughes <richard@hughsie.com>
#
# SPDX-License-Identifier: GPL-2.0+
#
# pylint: disable=fixme,too-many-instance-attributes,too-few-public-methods,too-many-statements

import os
import hashlib
import glob
import subprocess
import tempfile
import configparser
import datetime
import fnmatch

from lxml import etree as ET

from cabarchive import CabArchive, CabFile
from infparser import InfParser

from lvfs.models import Firmware, Component, ComponentIssue, Guid, Requirement, Checksum
from lvfs.util import _validate_guid, _markdown_from_root

class FileTooLarge(Exception):
    pass
class FileTooSmall(Exception):
    pass
class FileNotSupported(Exception):
    pass
class MetadataInvalid(Exception):
    pass

def _repackage_archive(filename, buf, tmpdir=None, flattern=True):
    """ Unpacks an archive (typically a .zip) into a CabArchive object """

    # write to temp file
    src = tempfile.NamedTemporaryFile(mode='wb',
                                      prefix='foreignarchive_',
                                      suffix=".zip",
                                      dir=tmpdir,
                                      delete=True)
    src.write(buf)
    src.flush()

    # decompress to a temp directory
    dest = tempfile.TemporaryDirectory(prefix='foreignarchive_')

    # work out what binary to use
    split = filename.rsplit('.', 1)
    if len(split) < 2:
        raise NotImplementedError('Filename not valid')
    if split[1] == 'zip':
        argv = ['/usr/bin/bsdtar', '--directory', dest.name, '-xvf', src.name]
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
    cabarchive = CabArchive()
    for fn in glob.glob(dest.name + '/**/*.*', recursive=True):
        with open(fn, 'rb') as f:
            fn = fn.replace('\\', '/')
            if flattern:
                fn = os.path.basename(fn)
            cabarchive[fn] = CabFile(f.read())
    return cabarchive

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

def _node_validate_text(node, minlen=0, maxlen=0, nourl=False, allow_none=False):
    """ Validates the style """

    # unwrap description
    if node.tag == 'description':
        text = _markdown_from_root(node)
    else:
        text = node.text
        if text:
            text = text.strip()
            for tag in ['<p>', '<li>', '<ul>', '<ol>']:
                if text.find(tag) != -1:
                    raise MetadataInvalid('{} cannot specify markup tag {}'.format(node.tag, tag))

    # invalid length
    if not text:
        if allow_none:
            return None
        raise MetadataInvalid('{} has no value'.format(node.tag))

    # some tags can be split for multiple models
    if node.tag in ['name']:
        textarray = text.split('/')
    else:
        textarray = [text]
    for textsplit in textarray:
        if minlen and len(textsplit) < minlen:
            raise MetadataInvalid('<{}> is too short: {}/{}'.format(node.tag, len(textsplit), minlen))
        if maxlen and len(textsplit) > maxlen:
            raise MetadataInvalid('<{}> is too long: {}/{}'.format(node.tag, len(textsplit), maxlen))

    # contains hyperlink
    if nourl:
        for urlhandler in ['http://', 'https://', 'ftp://']:
            if text.find(urlhandler) != -1:
                raise MetadataInvalid('{} cannot contain a hyperlink: {}'.format(node.tag, text))

    return text

class UploadedFile:

    def __init__(self, is_strict=True):
        """ default public attributes """

        self.fw = Firmware()
        self.is_strict = is_strict
        self.enable_inf_parsing = True
        self.fwupd_min_version = '0.8.0'    # a guess, but everyone should have this
        self.version_formats = {}
        self.category_map = {'X-Device' : 1}
        self.protocol_map = {}

        # strip out any unlisted files
        self.cabarchive_repacked = CabArchive()

        # private
        self._data_size = 0
        self.cabarchive_upload = None
        self._version_inf = None

    def _parse_inf(self, contents):

        # FIXME is banned...
        if contents.find('FIXME') != -1:
            raise MetadataInvalid('The inf file was not complete; Any FIXME text must be '
                                  'replaced with the correct values.')

        # check .inf file is valid
        try:
            cfg = InfParser(contents)
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
            self.fw.version_display = tmp[1]
        except configparser.NoOptionError as _:
            pass

        # this is optional, but if supplied must match the version in the XML
        # -- also note this will not work with multi-component .cab files
        if len(self.fw.mds) == 1 and self.fw.mds[0].version.isdigit():
            try:
                self._version_inf = cfg.get('Firmware_AddReg', 'HKR->FirmwareVersion')
                if self._version_inf.startswith('0x'):
                    self._version_inf = str(int(self._version_inf[2:], 16))
                if self._version_inf == '0':
                    self._version_inf = None
            except (configparser.NoOptionError, configparser.NoSectionError) as _:
                pass

    @staticmethod
    def _parse_release(md, release):

        # get description
        try:
            md.release_description = _node_validate_text(release.xpath('description')[0],
                                                         minlen=3, maxlen=1000, nourl=True)
        except IndexError as _:
            pass

        md.install_duration = int(release.get('install_duration', '0'))
        md.release_urgency = release.get('urgency')

        # date, falling back to timestamp
        if 'date' in release.attrib:
            try:
                dt = datetime.datetime.strptime(release.get('date'), "%Y-%m-%d")
                dt_utc = dt.replace(tzinfo=datetime.timezone.utc)
                md.release_timestamp = int(dt_utc.timestamp())
            except ValueError as e:
                raise MetadataInvalid('<release> has invalid date attribute: {}'.format(str(e)))
        elif 'timestamp' in release.attrib:
            try:
                md.release_timestamp = int(release.get('timestamp'))
            except ValueError as e:
                raise MetadataInvalid('<release> has invalid timestamp attribute: {}'.format(str(e)))
        else:
            raise MetadataInvalid('<release> had no date or timestamp attributes')

        # optional release tag
        if 'tag' in release.attrib:
            md.release_tag = release.attrib['tag']
            if len(md.release_tag) < 4:
                raise MetadataInvalid('<release> tag was too short to identify the firmware')
            md.add_keywords_from_string(md.release_tag, priority=6)

        # get list of CVEs
        for issue in release.xpath('issues/issue'):
            kind = issue.get('type')
            if not kind:
                raise MetadataInvalid('<issue> had no type attribute')
            if kind != 'cve':
                raise MetadataInvalid('<issue> type can only be \'cve\'')
            value = _node_validate_text(issue, minlen=3, maxlen=1000, nourl=True)
            md.issues.append(ComponentIssue(kind=kind, value=value))

        # get <url type="details">
        try:
            md.details_url = _node_validate_text(release.xpath('url[@type="details"]')[0],
                                                 minlen=12, maxlen=1000)
        except IndexError as _:
            pass

        # get <url type="source">
        try:
            md.source_url = _node_validate_text(release.xpath('url[@type="source"]')[0],
                                                minlen=12, maxlen=1000)
        except IndexError as _:
            pass

        # fix up hex version
        md.version = release.get('version')
        if not md.version:
            raise MetadataInvalid('<release> had no version attribute')
        if md.version.startswith('0x'):
            md.version = str(int(md.version[2:], 16))

        # ensure there's always a contents filename
        try:
            md.filename_contents = release.xpath('checksum[@target="content"]')[0].get('filename')
        except IndexError as _:
            pass
        if not md.filename_contents:
            md.filename_contents = 'firmware.bin'

        # ensure there's always a contents filename
        for csum in release.xpath('checksum[@target="device"]'):
            text = _node_validate_text(csum, minlen=32, maxlen=128)
            if csum.get('kind') == 'sha1':
                md.device_checksums.append(Checksum(value=text, kind='SHA1'))
            elif csum.get('kind') == 'sha256':
                md.device_checksums.append(Checksum(value=text, kind='SHA256'))
        if not md.filename_contents:
            md.filename_contents = 'firmware.bin'

    def _parse_component(self, component):

        # get priority
        md = Component()
        md.priority = int(component.get('priority', '0'))

        # check type
        if component.get('type') != 'firmware':
            raise MetadataInvalid('<component type="firmware"> required')

        # get <id>
        try:
            md.appstream_id = _node_validate_text(component.xpath('id')[0],
                                                  minlen=10, maxlen=256)
            if not md.appstream_id:
                raise MetadataInvalid('<id> value invalid')
            for char in md.appstream_id:
                if char.isspace():
                    raise MetadataInvalid('<id> Cannot contain spaces')
                if char in ['/', '\\']:
                    raise MetadataInvalid('<id> Cannot contain slashes')
                if char not in ['-', '_', '.'] and not char.isalnum():
                    raise MetadataInvalid('<id> Cannot contain {}'.format(char))
            if len(md.appstream_id.split('.')) < 4:
                raise MetadataInvalid('<id> Should contain at least 4 sections to identify the model')
        except IndexError as _:
            raise MetadataInvalid('<id> tag missing')

        # get <developer_name>
        try:
            md.developer_name = _node_validate_text(component.xpath('developer_name')[0],
                                                    minlen=3, maxlen=50, nourl=True)
            if md.developer_name == 'LenovoLtd.':
                md.developer_name = 'Lenovo Ltd.'
            md.add_keywords_from_string(md.developer_name, priority=10)
        except IndexError as _:
            raise MetadataInvalid('<developer_name> tag missing')
        if md.developer_name.find('@') != -1 or md.developer_name.find('_at_') != -1:
            raise MetadataInvalid('<developer_name> cannot contain an email address')

        # get <name>
        try:
            md.name = _node_validate_text(component.xpath('name')[0],
                                          minlen=3, maxlen=500)
            md.add_keywords_from_string(md.name, priority=3)

            # use categories instead
            if self.is_strict:
                category = {
                    'system' : 'X-System',
                    'device' : 'X-Device',
                    'bios' : 'X-System',
                    'me' : 'X-ManagementEngine',
                    'embedded' : 'X-EmbeddedController',
                    'controller' : 'X-EmbeddedController',
                }
                words = [word.lower() for word in md.name.split(' ')]
                for search in category:
                    if search in words:
                        raise MetadataInvalid('<name> tag should not contain {}, use '
                                              '<categories><category>{}'
                                              '</category></categories> instead'.\
                                              format(search, category[search]))

                # tokens banned outright
                for search in ['firmware', 'update', '(r)', '(c)']:
                    if search in words:
                        raise MetadataInvalid('<name> tag should not contain '
                                              'the word "{}"'.format(search))

                # should not include the vendor in the name
                if md.developer_name_display:
                    if md.developer_name_display.lower() in words:
                        raise MetadataInvalid('<name> tag should not contain '
                                              'the vendor name "{}"'.format(md.developer_name_display))
        except IndexError as _:
            raise MetadataInvalid('<name> tag missing')

        # get <summary>
        try:
            md.summary = _node_validate_text(component.xpath('summary')[0],
                                             minlen=10, maxlen=500)
            md.add_keywords_from_string(md.summary, priority=1)
        except IndexError as _:
            raise MetadataInvalid('<summary> tag missing')

        # get optional <name_variant_suffix>
        try:
            md.name_variant_suffix = _node_validate_text(component.xpath('name_variant_suffix')[0],
                                                         minlen=2, maxlen=500)
        except IndexError as _:
            pass

        # get optional <description}
        try:
            md.description = _node_validate_text(component.xpath('description')[0],
                                                 minlen=25, maxlen=1000, nourl=True)
        except IndexError as _:
            pass

        # get <metadata_license>
        if self.is_strict:
            try:
                md.metadata_license = _node_validate_text(component.xpath('metadata_license')[0])
                if md.metadata_license not in ['CC0-1.0', 'FSFAP',
                                               'CC-BY-3.0', 'CC-BY-SA-3.0', 'CC-BY-4.0', 'CC-BY-SA-4.0',
                                               'GFDL-1.1', 'GFDL-1.2', 'GFDL-1.3']:
                    raise MetadataInvalid('Invalid <metadata_license> tag of {}'.format(md.metadata_license))
            except AttributeError as _:
                raise MetadataInvalid('<metadata_license> tag')
            except IndexError as _:
                raise MetadataInvalid('<metadata_license> tag missing')

        # get <project_license>
        try:
            md.project_license = _node_validate_text(component.xpath('project_license')[0],
                                                     minlen=4, maxlen=50, nourl=True)
        except IndexError as _:
            raise MetadataInvalid('<project_license> tag missing')
        if not md.project_license:
            raise MetadataInvalid('<project_license> value invalid')

        # get <url type="homepage">
        try:
            md.url_homepage = _node_validate_text(component.xpath('url[@type="homepage"]')[0],
                                                  minlen=7, maxlen=1000)
        except IndexError as _:
            raise MetadataInvalid('<url type="homepage"> tag missing')
        if not md.url_homepage:
            raise MetadataInvalid('<url type="homepage"> value invalid')

        # add manually added keywords
        for keyword in component.xpath('keywords/keyword'):
            text = _node_validate_text(keyword, minlen=3, maxlen=50, nourl=True)
            if text.find(' ') != -1:
                raise MetadataInvalid('<keywords> cannot contain spaces')
            md.add_keywords_from_string(text, priority=5)

        # add provides
        for prov in component.xpath('provides/firmware[@type="flashed"]'):
            text = _node_validate_text(prov, minlen=5, maxlen=1000)
            if not _validate_guid(text):
                raise MetadataInvalid('The GUID {} was invalid.'.format(text))
            if text in ['230c8b18-8d9b-53ec-838b-6cfc0383493a',     # main-system-firmware
                        'f15aa55c-9cd5-5942-85ae-a6bf8740b96c',     # MST-panamera
                        'd6072785-6fc0-5f83-9d49-11376e7f48b1',     # MST-leaf
                        '49ec4eb4-c02b-58fc-8935-b1ee182405c7']:    # MST-tesla
                raise MetadataInvalid('The GUID {} is too generic'.format(text))
            md.guids.append(Guid(value=text))
        if not md.guids:
            raise MetadataInvalid('The metadata file did not provide any GUID.')

        # check the file didn't try to add it's own <require> on vendor-id
        # to work around the vendor-id security checks in fwupd
        if component.xpath('requires/firmware[text()="vendor-id"]'):
            raise MetadataInvalid('Firmware cannot specify vendor-id')

        # check only recognised requirements are added
        for req in component.xpath('requires/*'):
            if req.tag == 'firmware':
                text = _node_validate_text(req, minlen=3, maxlen=1000, allow_none=True)
                rq = Requirement(kind=req.tag,
                                 value=text,
                                 compare=req.get('compare'),
                                 version=req.get('version'),
                                 depth=req.get('depth', None))
                md.requirements.append(rq)
            elif req.tag == 'id':
                text = _node_validate_text(req, minlen=3, maxlen=1000)
                rq = Requirement(kind=req.tag,
                                 value=text,
                                 compare=req.get('compare'),
                                 version=req.get('version'))
                md.requirements.append(rq)
                if text == 'org.freedesktop.fwupd':
                    self.fwupd_min_version = req.get('version')
            elif req.tag == 'hardware':
                text = _node_validate_text(req, minlen=3, maxlen=1000)
                for req_value in text.split('|'):
                    rq = Requirement(kind=req.tag,
                                     value=req_value,
                                     compare=req.get('compare'),
                                     version=req.get('version'))
                    md.requirements.append(rq)
            else:
                raise MetadataInvalid('<{}> requirement was invalid'.format(req.tag))

        # from the first screenshot
        try:
            md.screenshot_caption = _node_validate_text(component.xpath('screenshots/screenshot/caption')[0],
                                                        minlen=8, maxlen=1000, nourl=True)
        except IndexError as _:
            pass
        try:
            md.screenshot_url = _node_validate_text(component.xpath('screenshots/screenshot/image')[0],
                                                    minlen=8, maxlen=1000)
        except IndexError as _:
            pass

        # allows OEM to hide the direct download link on the LVFS
        if component.xpath('custom/value[@key="LVFS::InhibitDownload"]'):
            md.inhibit_download = True

        # allows OEM to disable ignore all kinds of statistics on this firmware
        if component.xpath('custom/value[@key="LVFS::DoNotTrack"]'):
            md.fw.do_not_track = True

        # allows OEM to change the triplet (AA.BB.CCDD) to quad (AA.BB.CC.DD)
        try:
            version_format = _node_validate_text(component.xpath('custom/value[@key="LVFS::VersionFormat"]')[-1])
            if not self.version_formats:
                raise MetadataInvalid('Valid version formats have not been added')
            if version_format not in self.version_formats:
                raise MetadataInvalid('LVFS::VersionFormat can only be {}'.\
                                      format(','.join(self.version_formats.keys())))
            md.verfmt = self.version_formats[version_format]
        except IndexError as _:
            pass

        # enforce the VersionFormat if the version is an integer
        if self.is_strict and md.version:
            if md.version.isdigit() and not md.version_format:
                raise MetadataInvalid('LVFS::VersionFormat is required for integer version')

        # allows OEM to specify protocol
        try:
            text = _node_validate_text(component.xpath('custom/value[@key="LVFS::UpdateProtocol"]')[0])
            if text not in self.protocol_map:
                raise MetadataInvalid('No valid UpdateProtocol {} found'.format(text))
            md.protocol_id = self.protocol_map[text]
        except IndexError as _:
            pass

        # allows OEM to set banned country codes
        try:
            text = _node_validate_text(component.xpath('custom/value[@key="LVFS::BannedCountryCodes"]')[0],
                                       minlen=2, maxlen=1000, nourl=True)
            self.fw.banned_country_codes = text
        except IndexError as _:
            pass

        # should we parse the .inf file?
        try:
            text = _node_validate_text(component.xpath('custom/value[@key="LVFS::EnableInfParsing"]')[0],
                                       minlen=2, maxlen=10, nourl=True)
            if text == 'true':
                self.enable_inf_parsing = True
            elif text == 'false':
                self.enable_inf_parsing = False
            else:
                raise MetadataInvalid('LVFS::EnableInfParsing only allowed true or false, got {}'.format(text))
        except IndexError as _:
            pass

        # allows OEM to specify category
        for category in component.xpath('categories/category'):
            text = _node_validate_text(category, minlen=8, maxlen=50, nourl=True)
            if text in self.category_map:
                md.category_id = self.category_map[text]
                break

        # parse the default (first) release
        try:
            default_release = component.xpath('releases/release')[0]
        except IndexError as _:
            raise MetadataInvalid('The metadata file did not provide any releases')
        self._parse_release(md, default_release)

        # ensure the update description does not refer to a file in the archive
        if md.release_description:
            for word in md.release_description.split(' '):
                if word.find('.') == -1: # any word without a dot is not a fn
                    continue
                if word in self.cabarchive_upload:
                    raise MetadataInvalid('The release description should not reference other files.')

        # check the inf file matches up with the .xml file
        if self._version_inf and self._version_inf != md.version:
            raise MetadataInvalid('The inf Firmware_AddReg[HKR->FirmwareVersion] '
                                  '%s did not match the metainfo.xml value %s.'
                                  % (self._version_inf, md.version))

        # success
        return md

    def _parse_metainfo(self, cabfile):

        # check the file does not have any missing request.form
        if cabfile.buf.decode('utf-8', 'ignore').find('FIXME') != -1:
            raise MetadataInvalid('The metadata file was not complete; '
                                  'Any FIXME text must be replaced with the correct values.')

        # has UTF-8 BOM: https://en.wikipedia.org/wiki/Byte_order_mark
        if cabfile.buf.startswith(b'\xEF\xBB\xBF'):
            raise MetadataInvalid('The metadata file has a UTF-8 BOM that must be removed')

        # add to the archive
        self.cabarchive_repacked[cabfile.filename] = cabfile

        # parse MetaInfo file
        try:
            components = ET.fromstring(cabfile.buf).xpath('/component')
            if not components:
                raise MetadataInvalid('<component> tag missing')
            if len(components) > 1:
                raise MetadataInvalid('Multiple <component> tags')
        except UnicodeDecodeError as e:
            raise MetadataInvalid('The metadata file could not be parsed: {}'.format(str(e)))
        except ET.XMLSyntaxError as e:
            raise MetadataInvalid('The metadata file could not be parsed: {}'.format(str(e)))
        md = self._parse_component(components[0])
        md.release_download_size = self._data_size
        md.filename_xml = cabfile.filename

        # add the firmware.bin to the archive
        try:
            cabfile_fw = self.cabarchive_upload[md.filename_contents]
        except KeyError as _:
            raise MetadataInvalid('No {} found in the archive'.format(md.filename_contents))
        self.cabarchive_repacked[cabfile_fw.filename] = cabfile_fw
        md.checksum_contents_sha1 = hashlib.sha1(cabfile_fw.buf).hexdigest()
        md.checksum_contents_sha256 = hashlib.sha256(cabfile_fw.buf).hexdigest()
        md.release_installed_size = len(cabfile_fw.buf)
        self.fw.mds.append(md)

    def parse(self, filename, data, use_hashed_prefix=True):

        # check size
        self._data_size = len(data)
        if self._data_size > 104857600:
            raise FileTooLarge('File too large, limit is 100Mb')
        if self._data_size < 1024:
            raise FileTooSmall('File too small, minimum is 1k')

        # get new filename
        self.fw.checksum_upload_sha1 = hashlib.sha1(data).hexdigest()
        self.fw.checksum_upload_sha256 = hashlib.sha256(data).hexdigest()
        if use_hashed_prefix:
            self.fw.filename = self.fw.checksum_upload_sha256 + '-' + filename.replace('.zip', '.cab')
        else:
            self.fw.filename = filename.replace('.zip', '.cab')

        # parse the file
        try:
            if filename.endswith('.cab'):
                self.cabarchive_upload = CabArchive(data, flattern=True)
            else:
                self.cabarchive_upload = _repackage_archive(filename, data)
        except NotImplementedError as e:
            raise FileNotSupported('Invalid file type: %s' % str(e))

        # load metainfo files
        cabfiles = [cabfile for cabfile in self.cabarchive_upload.values()
                    if fnmatch.fnmatch(cabfile.filename, '*.metainfo.xml')]
        if not cabfiles:
            raise MetadataInvalid('The firmware file had no .metainfo.xml files')

        # parse each MetaInfo file
        for cabfile in cabfiles:
            self._parse_metainfo(cabfile)

        # verify .inf files if they exists
        inffiles = [cabfile for cabfile in self.cabarchive_upload.values()
                    if fnmatch.fnmatch(cabfile.filename, '*.inf')]
        for cabfile in inffiles:

            # add to the archive
            self.cabarchive_repacked[cabfile.filename] = cabfile

            # parse
            if self.enable_inf_parsing:
                encoding = detect_encoding_from_bom(cabfile.buf)
                self._parse_inf(cabfile.buf.decode(encoding))
