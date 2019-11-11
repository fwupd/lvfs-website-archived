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

    def test_docs(self):
        rv = self.app.get('/lvfs/docs/metainfo/protocol')
        assert 'com.hughski.colorhug' in rv.data.decode('utf-8'), rv.data.decode()

if __name__ == '__main__':
    unittest.main()
