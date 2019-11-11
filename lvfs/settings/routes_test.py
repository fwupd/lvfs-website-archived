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

    def test_settings(self):

        # open the main page
        self.login()
        rv = self.app.get('/lvfs/settings/')
        assert b'General server settings' in rv.data, rv.data
        assert b'ClamAV' in rv.data, rv.data

        # dig into the Windows Update page
        rv = self.app.get('/lvfs/settings/wu-copy')
        assert b'Copy files generated' in rv.data, rv.data
        assert b'value="enabled" checked/>' in rv.data, rv.data

        # change both values to False
        rv = self.app.post('/lvfs/settings/modify/wu-copy', data=dict(
            wu_copy_inf='disabled',
            wu_copy_cat='disabled',
        ), follow_redirects=True)
        assert b'Copy files generated' in rv.data, rv.data
        assert b'value="enabled" />' in rv.data, rv.data

        # and back to True
        rv = self.app.post('/lvfs/settings/modify/wu-copy', data=dict(
            wu_copy_inf='enabled',
            wu_copy_cat='enabled',
        ), follow_redirects=True)
        assert b'value="enabled" checked/>' in rv.data, rv.data

if __name__ == '__main__':
    unittest.main()
