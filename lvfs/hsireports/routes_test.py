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

    def test_hsireports(self):

        # upload a firmware that can receive a report
        self.login()
        self.upload(target='testing')

        # send empty
        rv = self.app.post('/lvfs/hsireports/upload')
        assert b'No data' in rv.data, rv.data

        # self less than what we need
        rv = self.app.post('/lvfs/hsireports/upload', data='{"MachineId" : "abc"}')
        assert b'invalid data, expected ReportVersion' in rv.data, rv.data

if __name__ == '__main__':
    unittest.main()
