#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2018-2019 Richard Hughes <richard@hughsie.com>
#
# SPDX-License-Identifier: GPL-2.0+
#
# pylint: disable=wrong-import-position,singleton-comparison

import os
import sys
import unittest

sys.path.append(os.path.realpath('.'))

from lvfs.testcase import LvfsTestCase

class LocalTestCase(LvfsTestCase):

    def test_devices(self):

        # upload to stable
        self.login()
        self.add_namespace(vendor_id=1)
        self.upload()
        self.run_cron_firmware()
        rv = self.app.post('/lvfs/firmware/1/promote/stable', follow_redirects=True)
        assert b'>stable<' in rv.data, rv.data.decode()
        self.logout()

        rv = self.app.get('/lvfs/devices/')
        assert 'ColorHug2 X-Device' in rv.data.decode('utf-8'), rv.data.decode()

        rv = self.app.get('/lvfs/devices/com.hughski.ColorHug2.firmware')
        assert 'Use a quicker start-up sequence' in rv.data.decode('utf-8'), rv.data.decode()

        rv = self.app.get('/lvfs/devices/com.hughski.ColorHug2.firmware/analytics')
        assert 'ChartDevice' in rv.data.decode('utf-8'), rv.data.decode()

if __name__ == '__main__':
    unittest.main()
