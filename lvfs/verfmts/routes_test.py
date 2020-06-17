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

    def test_verfmts(self):

        self.login()
        self.upload()
        rv = self.app.get('/lvfs/verfmts/')
        assert 'acme' not in rv.data.decode('utf-8'), rv.data

        # create
        rv = self.app.post('/lvfs/verfmts/create', data=dict(
            value='acme',
        ), follow_redirects=True)
        assert b'Added version format' in rv.data, rv.data.decode()
        rv = self.app.get('/lvfs/verfmts/')
        assert 'acme' in rv.data.decode('utf-8'), rv.data.decode()
        rv = self.app.post('/lvfs/verfmts/create', data=dict(
            value='acme',
        ), follow_redirects=True)
        assert b'Already exists' in rv.data, rv.data.decode()

        # modify
        rv = self.app.post('/lvfs/verfmts/3/modify', data=dict(
            name='ACME',
            example='1.2.3.4',
            fwupd_version='1.2.3',
        ), follow_redirects=True)
        assert b'Modified version format' in rv.data, rv.data.decode()
        rv = self.app.get('/lvfs/verfmts/')
        assert 'ACME' in rv.data.decode('utf-8'), rv.data.decode()

        # show
        rv = self.app.get('/lvfs/verfmts/3', follow_redirects=True)
        assert b'ACME' in rv.data, rv.data.decode()

        # delete
        rv = self.app.post('/lvfs/verfmts/3/delete', follow_redirects=True)
        assert b'Deleted version format' in rv.data, rv.data.decode()
        rv = self.app.get('/lvfs/verfmts/')
        assert 'acme' not in rv.data.decode('utf-8'), rv.data.decode()

if __name__ == '__main__':
    unittest.main()
