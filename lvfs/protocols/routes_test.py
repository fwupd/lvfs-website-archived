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

    def test_protocol(self):

        self.login()
        self.upload()
        rv = self.app.get('/lvfs/protocols/')
        assert 'com.acme' not in rv.data.decode('utf-8'), rv.data

        # create
        rv = self.app.post('/lvfs/protocols/create', data=dict(
            value='com.acme',
        ), follow_redirects=True)
        assert b'Added protocol' in rv.data, rv.data.decode()
        rv = self.app.get('/lvfs/protocols/')
        assert 'com.acme' in rv.data.decode('utf-8'), rv.data.decode()
        rv = self.app.post('/lvfs/protocols/create', data=dict(
            value='com.acme',
        ), follow_redirects=True)
        assert b'already exists' in rv.data, rv.data.decode()

        # modify
        rv = self.app.post('/lvfs/protocols/4/modify', data=dict(
            name='ACME',
            is_signed=True,
        ), follow_redirects=True)
        assert b'Modified protocol' in rv.data, rv.data.decode()
        rv = self.app.get('/lvfs/protocols/')
        assert 'ACME' in rv.data.decode('utf-8'), rv.data.decode()

        # delete
        rv = self.app.post('/lvfs/protocols/4/delete', follow_redirects=True)
        assert b'Deleted protocol' in rv.data, rv.data.decode()
        rv = self.app.get('/lvfs/protocols/')
        assert 'com.acme' not in rv.data.decode('utf-8'), rv.data.decode()

if __name__ == '__main__':
    unittest.main()
