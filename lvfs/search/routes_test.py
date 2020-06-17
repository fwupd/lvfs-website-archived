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

    def test_views_search(self):

        # upload firmware and move to stable
        self.login()
        self.add_namespace()
        self.upload(target='embargo')
        self.run_cron_firmware()
        self.run_cron_fwchecks()
        rv = self.app.post('/lvfs/firmware/1/promote/stable', follow_redirects=True)
        assert b'>stable<' in rv.data, rv.data

        # stats
        rv = self.app.get('/lvfs/analytics/search_history')
        assert b'No searches exist' in rv.data, rv.data

        # search logged in
        rv = self.app.get('/lvfs/search/firmware?value=colorhug2')
        assert b'ColorHug2 X-Device' in rv.data, rv.data
        rv = self.app.get('/lvfs/search/firmware?value=foobarbaz')
        assert b'No firmware has been uploaded or is visible by this user' in rv.data, rv.data
        self.logout()

        # search anon
        rv = self.app.get('/lvfs/search?value=colorhug2')
        assert b'ColorHug2 X-Device' in rv.data, rv.data

        # analytics
        self.login()
        rv = self.app.get('/lvfs/analytics/search_history')
        assert b'No searches exist' not in rv.data, rv.data

    def test_anon_search(self):

        # upload file with keywords
        self.login()
        self.add_namespace()
        self.upload(target='testing')
        self.logout()

        # search for something that does not exist
        rv = self.app.get('/lvfs/search?value=Edward')
        assert b'No results found for' in rv.data, rv.data

        # search for one defined keyword
        rv = self.app.get('/lvfs/search?value=Alice')
        assert b'ColorHug2' in rv.data, rv.data

        # search for one defined keyword, again
        rv = self.app.get('/lvfs/search?value=Alice')
        assert b'ColorHug2' in rv.data, rv.data

        # search for a keyword and a name match
        rv = self.app.get('/lvfs/search?value=Alice+Edward+ColorHug2')
        assert b'No results found for' in rv.data, rv.data

    def test_anon_search_not_promoted(self):

        # upload file with keywords
        self.login()
        self.add_namespace()
        self.upload(target='embargo')
        self.logout()

        # search for something that does not exist
        rv = self.app.get('/lvfs/search?value=alice')
        assert b'No results found for' in rv.data, rv.data

if __name__ == '__main__':
    unittest.main()
