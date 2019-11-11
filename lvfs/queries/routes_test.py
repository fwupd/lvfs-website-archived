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

    def test_yara_query(self):

        yara_rule = """
rule AMITestKey
{
    condition:
        true
}
"""

        # upload a file
        self.login()
        self.add_namespace()
        self.upload()

        # create a new query
        self.login()
        rv = self.app.post('/lvfs/queries/create', data=dict(value=yara_rule),
                           follow_redirects=True)
        assert b'added and will be run soon' in rv.data, rv.data.decode()

        # add duplicate
        rv = self.app.post('/lvfs/queries/create', data=dict(value=yara_rule),
                           follow_redirects=True)
        assert b'Already a query' in rv.data, rv.data.decode()

        rv = self.app.get('/lvfs/queries', follow_redirects=True)
        assert b'AMITestKey' in rv.data, rv.data.decode()

        rv = self.app.get('/lvfs/queries/1', follow_redirects=True)
        assert b'AMITestKey' in rv.data, rv.data.decode()

        self.run_cron_fwchecks()

        rv = self.app.get('/lvfs/queries', follow_redirects=True)
        assert b'0 out of 0' in rv.data, rv.data.decode()
        assert b'Retry' in rv.data, rv.data.decode()

        rv = self.app.get('/lvfs/queries/1/retry', follow_redirects=True)
        assert b'will be rerun soon' in rv.data, rv.data.decode()

        rv = self.app.get('/lvfs/queries/1/delete', follow_redirects=True)
        assert b'Deleted YARA query' in rv.data, rv.data.decode()

        rv = self.app.get('/lvfs/queries/1', follow_redirects=True)
        assert b'No YARA query found' in rv.data, rv.data.decode()

if __name__ == '__main__':
    unittest.main()
