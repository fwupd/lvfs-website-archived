#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2019 Richard Hughes <richard@hughsie.com>
# Licensed under the GNU General Public License Version 2
#
# pylint: disable=no-self-use,wrong-import-position

import struct
import zlib

import gi
gi.require_version('GCab', '1.0')
from gi.repository import GCab
from gi.repository import Gio
from gi.repository import GLib

from app.pluginloader import PluginBase, PluginError, PluginSettingBool
from app.util import _archive_get_files_from_glob, _get_absolute_path
from app.models import Test

class Plugin(PluginBase):
    def __init__(self):
        PluginBase.__init__(self)

    def name(self):
        return 'DFU'

    def summary(self):
        return 'Check the DFU firmware footer'

    def settings(self):
        s = []
        s.append(PluginSettingBool('dfu_check_footer', 'Enabled', True))
        return s

    def ensure_test_for_fw(self, fw):

        # only run for specific protocol
        require_test = False
        for md in fw.mds:
            if not md.protocol:
                continue
            if md.protocol.value == 'org.usb.dfu':
                require_test = True

        # add if not already exists
        if require_test:
            test = fw.find_test_by_plugin_id(self.id)
            if not test:
                test = Test(self.id, waivable=True)
                fw.tests.append(test)

    def run_test_on_fw(self, test, fw):

        # decompress firmware
        fn = _get_absolute_path(fw)
        try:
            istream = Gio.File.new_for_path(fn).read()
        except GLib.Error as e: # pylint: disable=catching-non-exception
            raise PluginError(e)
        cfarchive = GCab.Cabinet.new()
        cfarchive.load(istream)
        cfarchive.extract(None)

        # check each file
        for md in fw.mds:
            if md.protocol.value != 'org.usb.dfu':
                continue

            # get the component contents data
            cfs = _archive_get_files_from_glob(cfarchive, md.filename_contents)
            if not cfs or len(cfs) > 1:
                test.add_fail('Open', '%s not found in archive' % md.filename_contents)
                continue
            contents = cfs[0].get_bytes().get_data()

            # unpack the footer
            sz = len(contents)
            if sz < 16:
                test.add_fail('FileSize', '0x%x' % sz)
                # we have to abort here, no further tests are possible
                continue

            footer = contents[sz - 16:]
            try:
                data = struct.unpack('<HHHH3sBL', footer)
            except struct.error as e:
                test.add_fail('Footer', footer)
                # we have to abort here, no further tests are possible
                continue

            # check ucDfuSig
            if data[4] != b'UFD':
                test.add_fail('Footer Signature', '%s is not valid' % data[4])
                # we have to abort here, no further tests are possible
                continue

            # check bcdDevice
            if data[0] == 0x0000:
                test.add_fail('Device', '0x%04x is not valid' % data[0])

            # check idProduct
            if data[1] == 0x0000:
                test.add_fail('Product', '0x%04x is not valid' % data[1])

            # check idVendor
            if data[2] == 0x0000:
                test.add_fail('Vendor', '0x%04x is not valid' % data[2])

            # check bcdDFU
            if data[3] in [0x0101, 0x0100]:
                test.add_pass('DFU Version', '0x%04x' % data[3])
            else:
                test.add_fail('DFU Version', '0x%04x is not valid' % data[3])

            # check bLength
            if data[5] >= 10:
                test.add_pass('DFU Length', '0x%02x' % data[5])
            else:
                test.add_fail('DFU Length', '0x%02x is not valid' % data[5])

            # check dwCRC
            crc_correct = zlib.crc32(contents[:sz-4]) ^ 0xffffffff
            if data[6] == crc_correct:
                test.add_pass('CRC', '0x%04x' % data[6])
            else:
                test.add_fail('CRC', '0x%04x is not valid, expected 0x%04x' % (data[6], crc_correct))
