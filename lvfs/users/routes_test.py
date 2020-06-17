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

    def test_users(self):

        # login then add invalid users
        self.login()
        rv = self._add_user('testuser@fwupd.org', 'testgroup', 'unsuitable')
        assert b'requires at least one uppercase character' in rv.data, rv.data
        rv = self._add_user('testuser', 'testgroup', 'Pa$$w0rd')
        assert b'Invalid email address' in rv.data, rv.data
        rv = self._add_user('testuser@fwupd.org', 'XX', 'Pa$$w0rd')
        assert b'QA group invalid' in rv.data, rv.data

        # add a good user, and check the user and group was created
        rv = self._add_user('testuser@fwupd.org', 'testgroup', 'Pa$$w0rd')
        assert b'Added user' in rv.data, rv.data
        rv = self.app.get('/lvfs/users/')
        assert b'testuser' in rv.data, rv.data
        rv = self.app.get('/lvfs/users/3/admin')
        assert b'testuser@fwupd.org' in rv.data, rv.data
        rv = self.app.get('/lvfs/vendors/admin')
        assert b'testgroup' in rv.data, rv.data

        # modify an existing user as the admin
        rv = self.app.post('/lvfs/users/3/modify_by_admin', data=dict(
            auth_type='local',
            auth_warning='Caveat Emptor',
            is_qa='1',
            is_analyst='1',
            group_id='testgroup',
            display_name='Slightly Less Generic Name',
        ), follow_redirects=True)
        assert b'Updated profile' in rv.data, rv.data
        rv = self.app.get('/lvfs/users/3/admin')
        assert b'Slightly Less Generic Name' in rv.data, rv.data

        # ensure the user can log in
        self.logout()
        rv = self._login('testuser@fwupd.org')
        assert b'/lvfs/upload/firmware' in rv.data, rv.data
        assert b'Caveat Emptor' in rv.data, rv.data

        # ensure the user can change their own display name
        rv = self.app.post('/lvfs/users/3/modify', data=dict(
            display_name='Something Funky',
        ), follow_redirects=True)
        assert b'Updated profile' in rv.data, rv.data
        rv = self.app.get('/lvfs/profile')
        assert b'Something Funky' in rv.data, rv.data

        # ensure the user can change their own password
        rv = self.app.post('/lvfs/users/3/password', data=dict(
            password_old='not-even-close',
            password_new='Hi$$t0ry',
        ), follow_redirects=True)
        assert b'Incorrect existing password' in rv.data, rv.data
        rv = self.app.post('/lvfs/users/3/password', data=dict(
            password_old='Pa$$w0rd',
            password_new='Hi$$t0ry',
        ), follow_redirects=True)
        assert b'Updated profile' in rv.data, rv.data
        rv = self.app.get('/lvfs/profile')
        assert b'Something Funky' in rv.data, rv.data

        # try to self-delete
        rv = self.app.post('/lvfs/users/3/delete', follow_redirects=True)
        assert b'Only the admin team can access this resource' in rv.data, rv.data

        # delete the user as the admin
        self.logout()
        self.login()
        rv = self.app.post('/lvfs/users/3/delete', follow_redirects=True)
        assert b'Deleted user' in rv.data, rv.data
        rv = self.app.get('/lvfs/users/')
        assert b'testuser@fwupd.org' not in rv.data, rv.data

    def test_manager_users(self):

        # create a new vendor
        self.login()
        rv = self.app.post('/lvfs/vendors/create', data=dict(group_id='testvendor'),
                           follow_redirects=True)
        assert b'Added vendor' in rv.data, rv.data

        # set the username glob
        rv = self.app.post('/lvfs/vendors/2/modify_by_admin', data=dict(
            username_glob='*@testvendor.com,*@anothervendor.com',
        ), follow_redirects=True)
        assert b'Updated vendor' in rv.data, rv.data

        # create a manager user
        self.add_user('alice@testvendor.com', group_id='testvendor', is_vendor_manager=True)

        # log in as the manager
        self.logout()
        self.login('alice@testvendor.com')

        # try to add new user to new vendor with non-matching domain (fail)
        rv = self.app.post('/lvfs/vendors/2/user/create', data=dict(
            username='bob@hotmail.com',
            display_name='Generic Name',
        ), follow_redirects=True)
        assert b'Email address does not match account policy' in rv.data, rv.data

        # add new user with matching domain
        rv = self.app.post('/lvfs/vendors/2/user/create', data=dict(
            username='clara@testvendor.com',
            display_name='Generic Name',
        ), follow_redirects=True)
        assert b'Added user' in rv.data, rv.data

        # change the new user to allow a local login
        rv = self.app.post('/lvfs/users/4/modify_by_admin', data=dict(
            auth_type='local',
            password='Pa$$w0rd',
            is_vendor_manager=True,
        ), follow_redirects=True)
        assert b'Updated profile' in rv.data, rv.data

        # log in as the new user
        self.logout()
        self.login('clara@testvendor.com')

    def test_promote_as_user(self):

        # create User
        self.login()
        self.add_user('testuser@fwupd.org')
        self.logout()

        # login as user, upload file, then promote
        self.login('testuser@fwupd.org')
        self.upload()
        rv = self.app.post('/lvfs/firmware/1/promote/embargo', follow_redirects=True)
        assert b'Moved firmware' in rv.data, rv.data
        assert b'>embargo-testgroup<' in rv.data, rv.data
        rv = self.app.post('/lvfs/firmware/1/promote/embargo', follow_redirects=True)
        assert b'Firmware already in that target' in rv.data, rv.data
        assert b'>embargo-testgroup<' in rv.data, rv.data
        rv = self.app.post('/lvfs/firmware/1/promote/testing', follow_redirects=True)
        assert b'Permission denied' in rv.data, rv.data
        rv = self.app.post('/lvfs/firmware/1/promote/stable', follow_redirects=True)
        assert b'Permission denied' in rv.data, rv.data

        # demote back to private
        rv = self.app.post('/lvfs/firmware/1/promote/private', follow_redirects=True)
        assert b'>private<' in rv.data, rv.data
        assert b'Moved firmware' in rv.data, rv.data

    def test_promote_as_qa(self):

        # login as user, upload file, then promote FIXME: do as QA user, not admin
        self.login()
        self.add_namespace()
        self.upload()
        rv = self.app.post('/lvfs/firmware/1/promote/embargo', follow_redirects=True)
        assert b'Moved firmware' in rv.data, rv.data
        assert b'>embargo-admin<' in rv.data, rv.data
        self.run_cron_firmware()
        rv = self.app.post('/lvfs/firmware/1/promote/testing', follow_redirects=True)
        assert b'Moved firmware' in rv.data, rv.data
        assert b'>testing<' in rv.data, rv.data
        rv = self.app.post('/lvfs/firmware/1/promote/stable', follow_redirects=True)
        assert b'Moved firmware' in rv.data, rv.data
        assert b'>stable<' in rv.data, rv.data

        # build the pulp metadata
        self.logout()
        self.run_cron_metadata(['stable'])
        self.login()

        # demote back to testing then private
        rv = self.app.post('/lvfs/firmware/1/promote/testing', follow_redirects=True)
        assert b'Moved firmware' in rv.data, rv.data
        assert b'>testing<' in rv.data, rv.data
        rv = self.app.post('/lvfs/firmware/1/promote/private', follow_redirects=True)
        assert b'Moved firmware' in rv.data, rv.data
        assert b'>private<' in rv.data, rv.data

    def test_user_certificates(self):

        self.login()

        rv = self.app.get('/lvfs/profile')
        assert b'No client certificates have been uploaded' in rv.data, rv.data

        # upload invalid
        rv = self._add_certificate('contrib/Dockerfile')
        assert b'Certificate invalid, expected BEGIN CERTIFICATE' in rv.data, rv.data
        rv = self._add_certificate('contrib/bad.p7b')
        assert b'Certificate invalid, cannot parse' in rv.data, rv.data

        # upload valid
        rv = self._add_certificate()
        assert b'Added client certificate with serial 5f11a237b994931bbef869bd0153235874fa8f8b' in rv.data, rv.data

        # check exists
        rv = self.app.get('/lvfs/profile')
        assert b'5f11a237b994931bbef869bd0153235874fa8f8b' in rv.data, rv.data
        assert b'No client certificates have been uploaded' not in rv.data, rv.data

        # remove
        rv = self.app.post('/lvfs/users/certificate/remove/1', follow_redirects=True)
        assert b'Deleted certificate' in rv.data, rv.data
        rv = self.app.get('/lvfs/profile')
        assert b'5f11a237b994931bbef869bd0153235874fa8f8b' not in rv.data, rv.data

    def test_password_recovery(self):

        # add a user, then try to recover the password
        self.login()
        self.add_user('testuser@fwupd.org')
        self.logout()

        # not logged in
        rv = self.app.get('/lvfs/users/recover', follow_redirects=True)
        assert b'Forgot your password' in rv.data, rv.data
        rv = self.app.post('/lvfs/users/recover', data=dict(
            username='NOBODY@fwupd.org',
        ), follow_redirects=True)
        assert b'Unable to recover password as no username' in rv.data, rv.data
        rv = self.app.post('/lvfs/users/recover', data=dict(
            username='testuser@fwupd.org',
        ), follow_redirects=True)
        assert b'email has been sent with a recovery link' in rv.data, rv.data

        # get the recovery link from the admin event log
        uri = self._get_token_from_eventlog('link:')
        assert uri
        rv = self.app.get(uri, follow_redirects=True)
        assert b'password has been reset' in rv.data, rv.data

        # get the login link to check the email was sent
        password = self._get_token_from_eventlog('Password:')
        assert password is not None, password

        # try to use recovery link again
        rv = self.app.get(uri, follow_redirects=True)
        assert b'No user with that recovery password' in rv.data, rv.data
        assert b'password has been reset' not in rv.data, rv.data

        # try to log in with the new password
        self.login('testuser@fwupd.org', password=password)

if __name__ == '__main__':
    unittest.main()
