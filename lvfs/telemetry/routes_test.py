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

    def test_telemetry(self):

        # upload a firmware that can receive a report
        self.login()
        self.upload(target='testing')

        # send an update
        rv = self._report()
        assert b'"success": true' in rv.data, rv.data

        # download the firmware at least once
        self._download_firmware()

        # check the report appeared on download telemetry page
        self.run_cron_stats()
        rv = self.app.get('/lvfs/telemetry/0/download_cnt/down')
        assert b'ColorHug2' in rv.data, rv.data
        assert b'>1<' in rv.data, rv.data

        # check the report appeared on the success telemetry page
        self.run_cron_stats()
        rv = self.app.get('/lvfs/telemetry/0/success/down')
        assert b'ColorHug2' in rv.data, rv.data

if __name__ == '__main__':
    unittest.main()
