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

    def test_tests(self):

        self.login()
        self.upload()
        rv = self.app.get('/lvfs/tests/recent')
        assert 'check firmware for problems' in rv.data.decode('utf-8'), rv.data.decode()

        rv = self.app.get('/lvfs/tests/retry/1', follow_redirects=True)
        assert 'Test blocklist will be re-run soon' in rv.data.decode('utf-8'), rv.data.decode()

        rv = self.app.get('/lvfs/tests/pending')
        assert 'Test is pending' in rv.data.decode('utf-8'), rv.data.decode()

        rv = self.app.get('/lvfs/tests/')
        assert 'check firmware for problems' in rv.data.decode('utf-8'), rv.data.decode()

if __name__ == '__main__':
    unittest.main()
