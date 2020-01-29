#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2018-2019 Richard Hughes <richard@hughsie.com>
#
# SPDX-License-Identifier: GPL-2.0+
#
# pylint: disable=no-self-use

import struct
import uuid

from lvfs.pluginloader import PluginBase, PluginSettingBool
from lvfs.models import Test

class Plugin(PluginBase):
    def __init__(self):
        PluginBase.__init__(self)
        self.name = 'UEFI Capsule'
        self.summary = 'Check the UEFI capsule header and file structure'

    def settings(self):
        s = []
        s.append(PluginSettingBool('uefi_capsule_check_header', 'Enabled', True))
        return s

    def require_test_for_md(self, md):

        # only run for capsule updates
        if not md.protocol:
            return False
        if not md.blob:
            return False
        return md.protocol.value == 'org.uefi.capsule'

    def ensure_test_for_fw(self, fw):

        # add if not already exists
        test = fw.find_test_by_plugin_id(self.id)
        if not test:
            test = Test(self.id, waivable=True)
            fw.tests.append(test)

    def run_test_on_md(self, test, md):

        # unpack the header
        try:
            data = struct.unpack('<16sIII', md.blob[:28])
        except struct.error as _:
            test.add_fail('FileSize', '0x%x' % len(md.blob))
            # we have to abort here, no further tests are possible
            return

        # check the GUID
        guid = str(uuid.UUID(bytes_le=data[0]))
        referenced_guids = [gu.value for gu in md.guids]
        if guid == '00000000-0000-0000-0000-000000000000':
            test.add_fail('GUID', '%s is not valid' % guid)
        elif guid in referenced_guids:
            test.add_pass('GUID', guid)
        else:
            test.add_fail('GUID', '%s not found in %s' % (guid, ','.join(referenced_guids)))

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
        if data[3] == len(md.blob):
            test.add_pass('CapsuleImageSize', '0x%x' % data[3])
        else:
            test.add_fail('CapsuleImageSize',
                          '0x%x does not match file size 0x%x' % (data[3], len(md.blob)))
