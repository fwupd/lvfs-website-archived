#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2018-2019 Richard Hughes <richard@hughsie.com>
#
# SPDX-License-Identifier: GPL-2.0+
#
# pylint: disable=fixme,wrong-import-position,singleton-comparison

import os
import sys
import unittest

sys.path.append(os.path.realpath('.'))

from lvfs.testcase import LvfsTestCase

class LocalTestCase(LvfsTestCase):

    def test_upload_invalid(self):

        # upload something that isn't a cabinet archive
        self.login()
        rv = self._upload('contrib/Dockerfile', 'private')
        assert b'Failed to upload file' in rv.data, rv.data
        rv = self._upload('contrib/hughski-colorhug2-2.0.3.cab', 'NOTVALID')
        assert b'Target not valid' in rv.data, rv.data

    def test_upload_valid(self):

        # upload firmware
        self.login()
        rv = self._upload('contrib/hughski-colorhug2-2.0.3.cab', 'private')
        self._ensure_checksums_from_upload()
        assert self.checksum_upload_sha256 in rv.data.decode('utf-8'), rv.data
        rv = self.app.get('/lvfs/firmware/1/components')
        assert b'com.hughski.ColorHug2.firmware' in rv.data, rv.data

        # download
        self._download_firmware()

        # check analytics works
        uris = ['/lvfs/firmware/1/analytics',
                '/lvfs/firmware/1/analytics/clients',
                '/lvfs/firmware/1/analytics/reports']
        for uri in uris:
            rv = self.app.get(uri)
            assert b'favicon.ico' in rv.data, rv.data
            assert b'LVFS: Error' not in rv.data, rv.data

        # check component view shows GUID
        rv = self.app.get('/lvfs/components/1')
        assert b'2082b5e0-7a64-478a-b1b2-e3404fab6dad' in rv.data, rv.data

        # check private firmware isn't visible when not logged in
        rv = self.app.get('/lvfs/devices/')
        assert b'2082b5e0-7a64-478a-b1b2-e3404fab6dad' not in rv.data, rv.data
        rv = self.app.get('/lvfs/devices/com.hughski.ColorHug2.firmware')
        # FIXME is it a bug that we show the device exists even though it's not got any mds?
        assert b'MCDC04 errata' not in rv.data, rv.data
        rv = self.app.get('/lvfs/devices/')
        assert b'ColorHug' not in rv.data, rv.data
        self.login()

        # add namespace to allow promotion
        self.add_namespace()

        # promote the firmware to testing then stable
        self.run_cron_firmware()
        self.run_cron_fwchecks()
        rv = self.app.get('/lvfs/firmware/1/promote/testing',
                          follow_redirects=True)
        assert b'>testing<' in rv.data, rv.data
        assert b'>stable<' not in rv.data, rv.data
        rv = self.app.get('/lvfs/firmware/1/promote/stable',
                          follow_redirects=True)
        assert b'>stable<' in rv.data, rv.data

        # check it's now in the devicelist as anon
        self.logout()
        rv = self.app.get('/lvfs/devices/')
        assert b'ColorHug' in rv.data, rv.data
        rv = self.app.get('/lvfs/devices/com.hughski.ColorHug2.firmware')
        assert b'MCDC04 errata' in rv.data, rv.data
        self.login()

        # download it
        self._download_firmware()

        # test deleting the firmware
        self.delete_firmware()

        # download deleted file
        self._download_firmware()

        # re-upload the same file
        rv = self._upload('contrib/hughski-colorhug2-2.0.3.cab', 'private')
        assert b'Failed to upload file: A file with hash' in rv.data, rv.data

        # undelete it
        rv = self.app.get('/lvfs/firmware/1/undelete', follow_redirects=True)
        assert b'Firmware undeleted' in rv.data, rv.data

if __name__ == '__main__':
    unittest.main()
