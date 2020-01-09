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

    def test_login_logout(self):

        # test logging in and out
        rv = self._login('sign-test@fwupd.org', 'Pa$$w0rd')
        assert b'/lvfs/upload/firmware' in rv.data, rv.data
        rv = self._logout()
        rv = self._login('sign-test@fwupd.org', 'Pa$$w0rd')
        assert b'/lvfs/upload/firmware' in rv.data, rv.data
        rv = self._logout()
        assert b'/lvfs/upload/firmware' not in rv.data, rv.data
        rv = self._login('sign-test@fwupd.orgx', 'default')
        assert b'Incorrect username' in rv.data, rv.data
        rv = self._login('sign-test@fwupd.org', 'defaultx')
        assert b'Incorrect password' in rv.data, rv.data

    def test_eventlog(self):

        # login, upload then check both events were logged
        self.login()
        self.add_user('alice@fwupd.org')
        self.add_user('bob@fwupd.org', is_qa=True)
        self.add_user('mario@oem.com', is_qa=True, group_id='oem')
        self.logout()

        # alice cannot see her own event
        self.login('alice@fwupd.org')
        self.upload()
        rv = self.app.get('/lvfs/eventlog', follow_redirects=True)
        assert b'Unable to show event log for non-QA user' in rv.data, rv.data
        assert b'Uploaded file' not in rv.data, rv.data
        assert b'Logged in' not in rv.data, rv.data
        self.logout()

        # sign firmware, to create a admin-only event
        self.run_cron_firmware()

        # mario can't see anything as he's in a different vendor group
        self.login('mario@oem.com')
        rv = self.app.get('/lvfs/eventlog')
        assert b'Uploaded file' not in rv.data, rv.data
        assert b'Logged in' in rv.data, rv.data
        assert b'Signed firmware' not in rv.data, rv.data
        assert b'mario@oem.com' in rv.data, rv.data
        assert b'alice@fwupd.org' not in rv.data, rv.data
        self.logout()

        # bob is QA and can see just event for his vendor group
        self.login('bob@fwupd.org')
        rv = self.app.get('/lvfs/eventlog')
        assert b'Uploaded file' in rv.data, rv.data
        assert b'Logged in' in rv.data, rv.data
        assert b'>anonymous<' not in rv.data, rv.data
        assert b'Signed firmware' not in rv.data, rv.data
        assert b'mario@oem.com' not in rv.data, rv.data
        assert b'alice@fwupd.org' in rv.data, rv.data
        self.logout()

        # root can see everything
        self.login()
        rv = self.app.get('/lvfs/eventlog')
        assert b'Uploaded file' in rv.data, rv.data
        assert b'Logged in' in rv.data, rv.data
        assert b'Signed firmware' in rv.data, rv.data
        assert b'alice@fwupd.org' in rv.data, rv.data
        assert b'bob@fwupd.org' in rv.data, rv.data
        assert b'mario@oem.com' in rv.data, rv.data

    def test_nologin_required(self):

        # all these are viewable without being logged in
        uris = ['/',
                '/lvfs',
                '/vendors',
                '/users',
                '/developers',
                '/status',
                '/vendorlist',
                '/lvfs/devices',
                '/lvfs/devices/2082b5e0-7a64-478a-b1b2-e3404fab6dad',
                '/lvfs/docs/agreement',
                '/lvfs/docs/developers',
                '/lvfs/docs/users',
                '/lvfs/docs/vendors',
                '/users.html',
                '/vendors.html',
                '/developers.html',
                '/index.html',
               ]
        for uri in uris:
            rv = self.app.get(uri, follow_redirects=True)
            assert b'favicon.ico' in rv.data, rv.data
            assert b'LVFS: Error' not in rv.data, rv.data

    def test_fail_when_login_required(self):

        # all these are an error when not logged in
        uris = ['/lvfs/firmware']
        for uri in uris:
            rv = self.app.get(uri, follow_redirects=True)
            assert b'favicon.ico' in rv.data, rv.data
            assert b'Permission denied: Tried to request' in rv.data, rv.data

    def test_horrible_hackers(self):

        # all these are an error when not logged in
        uris = ['/wp-login.php']
        for uri in uris:
            rv = self.app.get(uri)
            assert b'bad karma' in rv.data, rv.data

if __name__ == '__main__':
    unittest.main()
