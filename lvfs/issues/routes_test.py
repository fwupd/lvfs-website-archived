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

    def test_issues_as_admin(self):

        # login, and check there are no issues
        self.login()
        rv = self.app.get('/lvfs/issues/')
        assert b'No issues have been created' in rv.data, rv.data

        # create an issue
        self.add_issue()

        # try to enable the issue without any conditions
        rv = self._enable_issue()
        assert b'Issue can not be enabled without conditions' in rv.data, rv.data

        # add Condition
        self.add_issue_condition()
        rv = self._add_issue_condition()
        assert b'Key DistroId already exists' in rv.data, rv.data

        # add another condition on the fwupd version
        rv = self._add_issue_condition(key='FwupdVersion', compare='gt', value='0.8.0')
        assert b'Added condition' in rv.data, rv.data

        # add another condition on the update string
        rv = self._add_issue_condition(key='UpdateError', compare='glob', value='*failed to make /boot/efi/EFI*')
        assert b'Added condition' in rv.data, rv.data

        # enable the issue
        self.enable_issue()

        # upload the firmware
        self.upload()

        # add a success report that should not match the issue
        rv = self._report()
        assert b'"success": true' in rv.data, rv.data
        assert b'The failure is a known issue' not in rv.data, rv.data

        # add a failed report matching the issue
        rv = self._report(updatestate=3)
        assert b'"success": true' in rv.data, rv.data
        assert b'The failure is a known issue' in rv.data, rv.data
        assert b'https://github.com/fwupd/fwupd/wiki/Arch-Linux' in rv.data, rv.data

        # add a report not matching the issue
        rv = self._report(updatestate=3, distro_id='rhel')
        assert b'The failure is a known issue' not in rv.data, rv.data
        assert b'https://github.com/fwupd/fwupd/wiki/Arch-Linux' not in rv.data, rv.data

        # remove Condition
        rv = self.app.post('/lvfs/issues/1/condition/1/delete', follow_redirects=True)
        assert b'Deleted condition' in rv.data, rv.data
        rv = self.app.post('/lvfs/issues/1/condition/1/delete', follow_redirects=True)
        assert b'No condition found' in rv.data, rv.data

        # delete the issue
        rv = self.app.post('/lvfs/issues/1/delete', follow_redirects=True)
        assert b'Deleted issue' in rv.data, rv.data
        rv = self.app.post('/lvfs/issues/1/delete', follow_redirects=True)
        assert b'No issue found' in rv.data, rv.data

    def test_issues_as_qa(self):

        # create QA:alice, QA:bob
        self.login()
        self.add_user('alice@fwupd.org', group_id='oem', is_qa=True)
        self.add_user('bob@fwupd.org', group_id='anotheroem', is_qa=True)

        # create a shared issue owned by admin
        self.add_issue(name='Shared', url='https://fwupd.org/')
        self.add_issue_condition()
        self.enable_issue()
        rv = self.app.get('/lvfs/issues/1/priority/down', follow_redirects=True)
        assert b'<!-- -1 -->' in rv.data, rv.data
        self.logout()

        # let alice create an issue
        self.login('alice@fwupd.org')
        self.add_issue(issue_id=2, name='Secret')
        self.add_issue_condition(issue_id=2)
        self.enable_issue(issue_id=2)
        rv = self.app.get('/lvfs/issues/2/priority/up', follow_redirects=True)
        assert b'<!-- 1 -->' in rv.data, rv.data
        self.logout()

        # bob can only see the admin issue, not the one from alice
        self.login('bob@fwupd.org')
        rv = self.app.get('/lvfs/issues/')
        assert b'Shared' in rv.data, rv.data
        assert b'Secret' not in rv.data, rv.data

        # we can only view the admin issue
        rv = self.app.post('/lvfs/issues/1/condition/1/delete', follow_redirects=True)
        assert b'Unable to delete condition from issue' in rv.data, rv.data
        rv = self.app.post('/lvfs/issues/1/delete', follow_redirects=True)
        assert b'Unable to delete report' in rv.data, rv.data
        rv = self.app.get('/lvfs/issues/1/details')
        assert b'Shared' in rv.data, rv.data

        # we can't do anything to the secret issue
        rv = self.app.post('/lvfs/issues/2/condition/1/delete', follow_redirects=True)
        assert b'Unable to delete condition from issue' in rv.data, rv.data
        rv = self.app.post('/lvfs/issues/2/delete', follow_redirects=True)
        assert b'Unable to delete report' in rv.data, rv.data
        rv = self.app.get('/lvfs/issues/2/details', follow_redirects=True)
        assert b'Unable to view issue details' in rv.data, rv.data
        rv = self.app.get('/lvfs/issues/2/priority/up', follow_redirects=True)
        assert b'Unable to change issue priority' in rv.data, rv.data

if __name__ == '__main__':
    unittest.main()
