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

    def test_cron_metadata(self):

        # verify all metadata is in good shape
        self.login()
        rv = self.app.get('/lvfs/metadata/')
        assert b'Remote will be signed with' not in rv.data, rv.data

        # upload file, dirtying the admin-embargo remote
        self.upload('embargo')
        rv = self.app.get('/lvfs/metadata/')
        assert b'Remote will be signed with' in rv.data, rv.data.decode()

        # run the cron job manually
        self.run_cron_metadata(['embargo-admin'])

        # verify all metadata is in good shape
        rv = self.app.get('/lvfs/metadata/')
        assert b'Remote will be signed with' not in rv.data, rv.data

    def test_metadata_rebuild(self):

        # create ODM user as admin
        self.login()
        self.add_user('testuser@fwupd.org')
        self.add_namespace()
        self.logout()

        # login and upload firmware to embargo
        self.login('testuser@fwupd.org')
        self.upload(target='embargo')

        # relogin as admin and rebuild metadata
        self.logout()
        self.login()
        rv = self.app.get('/lvfs/metadata/rebuild', follow_redirects=True)
        assert b'Metadata will be rebuilt' in rv.data, rv.data

        # check the remote is generated
        rv = self.app.get('/lvfs/metadata/testgroup')
        assert b'Title=Embargoed for testgroup' in rv.data, rv.data

if __name__ == '__main__':
    unittest.main()
