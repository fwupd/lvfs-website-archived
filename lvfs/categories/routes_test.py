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

    def test_categories(self):

        self.login()
        self.upload()
        rv = self.app.get('/lvfs/categories/')
        assert 'X-Acme' not in rv.data.decode('utf-8'), rv.data

        # create
        rv = self.app.post('/lvfs/categories/create', data=dict(
            value='X-Acme',
        ), follow_redirects=True)
        assert b'Added category' in rv.data, rv.data.decode()
        rv = self.app.get('/lvfs/categories/')
        assert 'X-Acme' in rv.data.decode('utf-8'), rv.data.decode()
        rv = self.app.post('/lvfs/categories/create', data=dict(
            value='X-Acme',
        ), follow_redirects=True)
        assert b'already exists' in rv.data, rv.data.decode()

        # modify
        rv = self.app.post('/lvfs/categories/3/modify', data=dict(
            name='ACME',
            example='1.2.3.4',
            fwupd_version='1.2.3',
        ), follow_redirects=True)
        assert b'Modified category' in rv.data, rv.data.decode()
        rv = self.app.get('/lvfs/categories/')
        assert 'ACME' in rv.data.decode('utf-8'), rv.data.decode()

        # show
        rv = self.app.get('/lvfs/categories/3', follow_redirects=True)
        assert b'ACME' in rv.data, rv.data.decode()

        # delete
        rv = self.app.post('/lvfs/categories/3/delete', follow_redirects=True)
        assert b'Deleted category' in rv.data, rv.data.decode()
        rv = self.app.get('/lvfs/categories/')
        assert 'X-Acme' not in rv.data.decode('utf-8'), rv.data.decode()

if __name__ == '__main__':
    unittest.main()
