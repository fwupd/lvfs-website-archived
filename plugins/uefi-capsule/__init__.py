#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2018-2019 Richard Hughes <richard@hughsie.com>
# Licensed under the GNU General Public License Version 2
#
# pylint: disable=no-self-use,wrong-import-position

import struct
import uuid

import gi
gi.require_version('GCab', '1.0')
from gi.repository import GCab
from gi.repository import Gio
from gi.repository import GLib

from app.pluginloader import PluginBase, PluginError, PluginSettingBool
from app.util import _get_settings, _archive_get_files_from_glob, _get_absolute_path
from app.models import Test

class Plugin(PluginBase):
    def __init__(self):
        PluginBase.__init__(self)

    def name(self):
        return 'UEFI Capsule'

    def summary(self):
        return 'Check the UEFI capsule header and file structure'

    def settings(self):
        s = []
        s.append(PluginSettingBool('uefi_capsule_check_header', 'Check Header', True))
        return s

    def ensure_test_for_fw(self, fw):

        # get settings
        settings = _get_settings('uefi_capsule')
        if settings['uefi_capsule_check_header'] != 'enabled':
            return

        # only run for capsule updates
        require_test = False
        for md in fw.mds:
            if not md.protocol:
                continue
            if md.protocol.value == 'org.uefi.capsule':
                require_test = True

        # add if not already exists
        if require_test:
            test = fw.find_test_by_plugin_id(self.id)
            if not test:
                test = Test(self.id, waivable=True)
                fw.tests.append(test)

    def run_test_on_fw(self, test, fw):

        # get settings
        settings = _get_settings('uefi_capsule')
        if settings['uefi_capsule_check_header'] != 'enabled':
            return

        # decompress firmware
        fn = _get_absolute_path(fw)
        try:
            istream = Gio.File.new_for_path(fn).read()
        except GLib.Error as e: # pylint: disable=catching-non-exception
            raise PluginError(e)
        cfarchive = GCab.Cabinet.new()
        cfarchive.load(istream)
        cfarchive.extract(None)

        # check each capsule
        for md in fw.mds:
            if md.protocol.value != 'org.uefi.capsule':
                continue

            # get the component contents data
            cfs = _archive_get_files_from_glob(cfarchive, md.filename_contents)
            if not cfs or len(cfs) > 1:
                test.add_fail('Open', '%s not found in archive' % md.filename_contents)
                continue
            contents = cfs[0].get_bytes().get_data()

            # unpack the header
            try:
                data = struct.unpack('<16sIII', contents[:28])
            except struct.error as e:
                test.add_fail('FileSize', '0x%x' % len(contents))
                # we have to abort here, no further tests are possible
                continue

            # check the GUID
            guid = str(uuid.UUID(bytes_le=data[0]))
            referenced_guids = []
            for gu in md.guids:
                referenced_guids.append(gu.value)
            if guid == '00000000-0000-0000-0000-000000000000':
                test.add_fail('GUID', '%s is not valid' % guid)
            elif guid in referenced_guids:
                test.add_pass('GUID', guid)
            else:
                test.add_fail('GUID', '%s not found in %s' % (guid, referenced_guids))

            # check the header size
            if data[1] == 0:
                test.add_fail('HeaderSize', '0x%x' % data[1])
            else:
                test.add_pass('HeaderSize', '0x%x' % data[1])

            # check if the flags are sane
            CAPSULE_FLAGS_PERSIST_ACROSS_RESET = 0x00010000
            CAPSULE_FLAGS_POPULATE_SYSTEM_TABLE = 0x00020000
            CAPSULE_FLAGS_INITIATE_RESET = 0x00040000
            if data[2] & CAPSULE_FLAGS_POPULATE_SYSTEM_TABLE > 0 and \
               data[2] & CAPSULE_FLAGS_PERSIST_ACROSS_RESET == 0:
                test.add_fail('Flags', '0x%x -- POPULATE_SYSTEM_TABLE requires PERSIST_ACROSS_RESET' % data[2])
            elif data[2] & CAPSULE_FLAGS_INITIATE_RESET > 0 and \
                 data[2] & CAPSULE_FLAGS_PERSIST_ACROSS_RESET == 0:
                test.add_fail('Flags', '0x%x -- INITIATE_RESET requires PERSIST_ACROSS_RESET' % data[2])
            else:
                test.add_pass('Flags', '0x%x' % data[2])

            # check the capsule image size
            if data[3] == len(contents):
                test.add_pass('CapsuleImageSize', '0x%x' % data[3])
            else:
                test.add_fail('CapsuleImageSize',
                              '0x%x does not match file size 0x%x' % (data[3], len(contents)))
