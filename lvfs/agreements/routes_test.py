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

    def test_agreement_decline(self):

        # add a user and try to upload firmware without signing the agreement
        self.login()
        self.add_user('testuser@fwupd.org')
        self.logout()
        self.login('testuser@fwupd.org')
        rv = self.app.get('/lvfs/agreements/1/decline', follow_redirects=True)
        assert b'Recorded decline of the agreement' in rv.data, rv.data
        rv = self._upload('contrib/hughski-colorhug2-2.0.3.cab', 'private')
        assert b'User has not signed legal agreement' in rv.data, rv.data

    def test_agreement_list_modify_add_delete(self):

        # get the default one
        self.login()
        rv = self.app.get('/lvfs/agreements/list')
        assert b'New agreement text' in rv.data, rv.data

        # modify the agreement
        rv = self.app.post('/lvfs/agreements/1/modify', data=dict(
            version=12345,
            text='DONOTSIGN',
        ), follow_redirects=True)
        assert b'Modified agreement' in rv.data, rv.data
        assert b'12345' in rv.data, rv.data
        assert b'DONOTSIGN' in rv.data, rv.data
        rv = self.app.get('/lvfs/agreements/list')
        assert b'12345' in rv.data, rv.data
        assert b'DONOTSIGN' in rv.data, rv.data

        # create a new one
        rv = self.app.get('/lvfs/agreements/create', follow_redirects=True)
        assert b'Created agreement' in rv.data, rv.data
        rv = self.app.get('/lvfs/agreements/list')
        assert b'New agreement text' in rv.data, rv.data

        # delete the original one
        rv = self.app.get('/lvfs/agreements/1/delete', follow_redirects=True)
        assert b'Deleted agreement' in rv.data, rv.data
        rv = self.app.get('/lvfs/agreements/list')
        assert b'DONOTSIGN' not in rv.data, rv.data

if __name__ == '__main__':
    unittest.main()
