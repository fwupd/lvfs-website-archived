#!/usr/bin/python2
# -*- coding: utf-8 -*-
#
# Copyright (C) 2018 Richard Hughes <richard@hughsie.com>
# Licensed under the GNU General Public License Version 2
#
# pylint: disable=no-self-use

from __future__ import print_function

import os
import struct
import uuid

from app.pluginloader import PluginBase, PluginError, PluginSettingBool
from app.util import _get_firmware_contents_from_archive, _get_settings
from app.models import Assay

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

    def ensure_assay_for_md(self, md):

        # get settings
        settings = _get_settings('uefi_capsule_check_header')
        if settings['uefi_capsule_check_header'] != 'enabled':
            return

        # only run for capsule updates
        if not md.protocol:
            return
        if md.protocol.value != 'org.uefi.capsule':
            return

        # add if not already exists
        assay = md.find_assay_by_plugin_id(self.id)
        if not assay:
            assay = Assay(self.id, waivable=True)
            md.assays.append(assay)

    def run_assay_on_md(self, assay, md):

        # get settings
        settings = _get_settings('uefi_capsule_check_header')
        if settings['uefi_capsule_check_header'] != 'enabled':
            return

        # decompress firmware
        try:
            contents = _get_firmware_contents_from_archive(md)
        except RuntimeError as e:
            assay.add_fail('Open', 'Cannot load %s: %s' % (md.filename_contents, str(e)))
            # we have to abort here, no further tests are possible
            return

        # unpack the header
        try:
            data = struct.unpack('<16sIII', contents[:28])
        except struct.error as e:
            assay.add_fail('FileSize', len(contents))
            # we have to abort here, no further tests are possible
            return

        # check the GUID
        guid = str(uuid.UUID(bytes_le=data[0]))
        referenced_guids = []
        for gu in md.guids:
            referenced_guids.append(gu.value)
        if guid == '00000000-0000-0000-0000-000000000000':
            assay.add_fail('GUID', '%s is not valid' % guid)
        elif guid in referenced_guids:
            assay.add_pass('GUID', guid)
        else:
            assay.add_fail('GUID', '%s not found in %s' % (guid, referenced_guids))

        # check the header size
        if data[1] % 4096 == 0:
            assay.add_pass('HeaderSize', data[1])
        else:
            assay.add_fail('HeaderSize', '0x%x not aligned to 4kB' % data[1])

        # check if the flags are sane
        CAPSULE_FLAGS_PERSIST_ACROSS_RESET = 0x00010000
        CAPSULE_FLAGS_POPULATE_SYSTEM_TABLE = 0x00020000
        CAPSULE_FLAGS_INITIATE_RESET = 0x00040000
        if data[2] & CAPSULE_FLAGS_POPULATE_SYSTEM_TABLE > 0 and \
           data[2] & CAPSULE_FLAGS_PERSIST_ACROSS_RESET == 0:
            assay.add_fail('Flags', '0x%x -- POPULATE_SYSTEM_TABLE requires PERSIST_ACROSS_RESET' % data[2])
        elif data[2] & CAPSULE_FLAGS_INITIATE_RESET > 0 and \
             data[2] & CAPSULE_FLAGS_PERSIST_ACROSS_RESET == 0:
            assay.add_fail('Flags', '0x%x -- INITIATE_RESET requires PERSIST_ACROSS_RESET' % data[2])
        else:
            assay.add_pass('Flags', '0x%x' % data[2])

        # check the capsule image size
        if data[3] == len(contents):
            assay.add_pass('CapsuleImageSize', data[3])
        else:
            assay.add_fail('CapsuleImageSize',
                           '0x%x does not match file size 0x%x' % (data[3], len(contents)))
