#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2020 Richard Hughes <richard@hughsie.com>
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

    def test_claim(self):

        self.login()
        self.upload()
        rv = self.app.get('/lvfs/claims/')
        assert 'biosguard' not in rv.data.decode('utf-8'), rv.data

        # create
        rv = self.app.post('/lvfs/claims/create', data=dict(
            kind='biosguard',
        ), follow_redirects=True)
        assert b'Added claim' in rv.data, rv.data.decode()
        rv = self.app.get('/lvfs/claims/')
        assert 'biosguard' in rv.data.decode('utf-8'), rv.data.decode()
        rv = self.app.post('/lvfs/claims/create', data=dict(
            kind='biosguard',
        ), follow_redirects=True)
        assert b'already exists' in rv.data, rv.data.decode()

        # modify
        rv = self.app.post('/lvfs/claims/1/modify', data=dict(
            summary='BIOSGuard',
        ), follow_redirects=True)
        assert b'Modified claim' in rv.data, rv.data.decode()
        rv = self.app.get('/lvfs/claims/')
        assert 'BIOSGuard' in rv.data.decode('utf-8'), rv.data.decode()

        # delete
        rv = self.app.get('/lvfs/claims/1/delete', follow_redirects=True)
        assert b'Deleted claim' in rv.data, rv.data.decode()
        rv = self.app.get('/lvfs/claims/')
        assert 'biosguard' not in rv.data.decode('utf-8'), rv.data.decode()

if __name__ == '__main__':
    unittest.main()
