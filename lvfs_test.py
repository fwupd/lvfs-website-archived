#!/usr/bin/python2
# -*- coding: utf-8 -*-
#
# Copyright (C) 2018 Richard Hughes <richard@hughsie.com>
# Licensed under the GNU General Public License Version 2
#
# pylint: disable=fixme,too-many-public-methods

from __future__ import print_function

import os
import unittest
import tempfile

class LvfsTestCase(unittest.TestCase):

    def setUp(self):

        # create new database
        self.db_fd, self.db_filename = tempfile.mkstemp()
        self.db_uri = 'sqlite:///' + self.db_filename

        # write out custom settings file
        self.cfg_filename = '/tmp/foo.cfg'
        cfgfile = open(self.cfg_filename, 'w')
        cfgfile.write('\n'.join([
            "DATABASE = '%s'" % self.db_uri,
            "DOWNLOAD_DIR = '/tmp'",
            "TESTING = True",
            ]))
        cfgfile.close()
        os.environ['LVFS_CUSTOM_SETTINGS'] = self.cfg_filename

        # create instance
        import app as lvfs
        from app import db
        self.app = lvfs.app.test_client()
        with lvfs.app.app_context():
            db.drop_db()
            db.init_db()

        # ensure the plugins settings are set up
        self.login()
        self.app.get('/lvfs/settings_create')
        self.logout()

    def tearDown(self):
        os.close(self.db_fd)
        os.unlink(self.db_filename)
        os.unlink(self.cfg_filename)

    def _login(self, username, password):
        return self.app.post('/lvfs/login', data=dict(
            username=username,
            password=password
        ), follow_redirects=True)

    def _logout(self):
        return self.app.get('/lvfs/logout', follow_redirects=True)

    def login(self, username='admin', password='Pa$$w0rd'):
        rv = self._login(username, password)
        assert b'/lvfs/upload' in rv.data, rv.data
        assert b'Incorrect username or password' not in rv.data, rv.data

    def logout(self):
        rv = self._logout()
        assert b'/lvfs/upload' not in rv.data, rv.data

    def delete_firmware(self, firmware_id='e133637179fa7c37d7a36657c7e302edce3d0fce'):
        rv = self.app.get('/lvfs/firmware/%s/delete_force' % firmware_id,
                          follow_redirects=True)
        assert b'Firmware deleted' in rv.data, rv.data

    def _add_user(self, username, group_id, password, email):
        return self.app.post('/lvfs/user/add', data=dict(
            password_new=password,
            username_new=username,
            group_id=group_id,
            name='Generic Name',
            email=email,
        ), follow_redirects=True)

    def add_user(self, username='testuser', group_id='testgroup',
                 password='Pa$$w0rd', email='test@test.com',
                 is_qa=False, is_analyst=False):
        rv = self._add_user(username, group_id, password, email)
        assert b'Added user' in rv.data, rv.data
        if is_qa or is_analyst:
            data = {'is_enabled': '1'}
            if is_qa:
                data['is_qa'] = '1'
            if is_analyst:
                data['is_analyst'] = '1'
            rv = self.app.post('/lvfs/user/%s/modify_by_admin' % username,
                               data=data, follow_redirects=True)
            assert b'Updated profile' in rv.data, rv.data

    def _upload(self, filename, target):
        fd = open(filename, 'rb')
        return self.app.post('/lvfs/upload', data={
            'target': target,
            'file': (fd, filename)
        }, follow_redirects=True)

    def upload(self, target='private'):
        rv = self._upload('contrib/hughski-colorhug2-2.0.3.cab', target)
        assert b'Uploaded firmware' in rv.data, rv.data
        assert b'com.hughski.ColorHug2.firmware' in rv.data, rv.data
        assert b'e133637179fa7c37d7a36657c7e302edce3d0fce' in rv.data, rv.data

    def test_login_logout(self):

        # test logging in and out
        rv = self._login('admin', 'Pa$$w0rd')
        assert b'/lvfs/upload' in rv.data, rv.data
        rv = self._logout()
        assert b'/lvfs/upload' not in rv.data, rv.data
        rv = self._login('adminx', 'default')
        assert b'Incorrect username or password' in rv.data, rv.data
        rv = self._login('admin', 'defaultx')
        assert b'Incorrect username or password' in rv.data, rv.data

    def test_upload_invalid(self):

        # upload something that isn't a cabinet archive
        self.login()
        rv = self._upload('contrib/Dockerfile', 'private')
        assert b'Failed to upload file' in rv.data, rv.data
        rv = self._upload('contrib/hughski-colorhug2-2.0.3.cab', 'NOTVALID')
        assert b'Target not valid' in rv.data, rv.data

    def test_upload_valid(self):

        # upload firmware
        self.login()
        rv = self._upload('contrib/hughski-colorhug2-2.0.3.cab', 'private')
        assert b'com.hughski.ColorHug2.firmware' in rv.data, rv.data
        assert b'e133637179fa7c37d7a36657c7e302edce3d0fce' in rv.data, rv.data

        # check analytics works
        uris = ['/lvfs/firmware/e133637179fa7c37d7a36657c7e302edce3d0fce/analytics',
                '/lvfs/firmware/e133637179fa7c37d7a36657c7e302edce3d0fce/analytics/clients',
                '/lvfs/firmware/e133637179fa7c37d7a36657c7e302edce3d0fce/analytics/month',
                '/lvfs/firmware/e133637179fa7c37d7a36657c7e302edce3d0fce/analytics/reports',
                '/lvfs/firmware/e133637179fa7c37d7a36657c7e302edce3d0fce/analytics/year']
        for uri in uris:
            rv = self.app.get(uri)
            assert b'favicon.ico' in rv.data, rv.data
            assert b'LVFS: Error' not in rv.data, rv.data

        # check component view shows GUID
        rv = self.app.get('/lvfs/component/1')
        assert b'2082b5e0-7a64-478a-b1b2-e3404fab6dad' in rv.data, rv.data

        # check devices page shows private firmware as admin -- and hidden when anon
        rv = self.app.get('/lvfs/device')
        assert b'2082b5e0-7a64-478a-b1b2-e3404fab6dad' in rv.data, rv.data
        rv = self.app.get('/lvfs/device/2082b5e0-7a64-478a-b1b2-e3404fab6dad')
        assert b'MCDC04 errata' in rv.data, rv.data
        self.logout()

        # check private firmware isn't visible when not logged in
        rv = self.app.get('/lvfs/device')
        assert b'2082b5e0-7a64-478a-b1b2-e3404fab6dad' not in rv.data, rv.data
        rv = self.app.get('/lvfs/device/2082b5e0-7a64-478a-b1b2-e3404fab6dad')
        # FIXME is it a bug that we show the device exists even though it's not got any mds?
        assert b'MCDC04 errata' not in rv.data, rv.data
        rv = self.app.get('/lvfs/devicelist')
        assert b'ColorHug' not in rv.data, rv.data
        self.login()

        # promote the firmware to testing then stable
        rv = self.app.get('/lvfs/firmware/e133637179fa7c37d7a36657c7e302edce3d0fce/promote/testing',
                          follow_redirects=True)
        assert b'>testing<' in rv.data, rv.data
        assert b'>stable<' not in rv.data, rv.data
        rv = self.app.get('/lvfs/firmware/e133637179fa7c37d7a36657c7e302edce3d0fce/promote/stable',
                          follow_redirects=True)
        assert b'>stable<' in rv.data, rv.data
        assert b'>testing<' not in rv.data, rv.data

        # check it's now in the devicelist as anon
        self.logout()
        rv = self.app.get('/lvfs/devicelist')
        assert b'ColorHug' in rv.data, rv.data
        self.login()

        # test deleting the firmware
        rv = self.app.get('/lvfs/firmware/e133637179fa7c37d7a36657c7e302edce3d0fce/delete')
        assert b'Irrevocably Remove Firmware' in rv.data, rv.data
        self.delete_firmware()

    def test_user_delete_wrong_user(self):

        # create user
        self.login()
        self.add_user('testuser')
        self.add_user('otheruser')
        self.logout()

        # upload as testuser
        self.login('testuser')
        self.upload()
        self.logout()

        # try to delete as otheruser
        self.login('otheruser')
        rv = self.app.get('/lvfs/firmware/e133637179fa7c37d7a36657c7e302edce3d0fce/delete_force',
                          follow_redirects=True)
        assert b'Firmware deleted' not in rv.data, rv.data
        assert b'Insufficient permissions to delete firmware' in rv.data, rv.data

    def test_user_delete_qa_wrong_group(self):

        # create user
        self.login()
        self.add_user('testuser')
        self.add_user('otheruser', 'different_group', is_qa=True)
        self.logout()

        # upload as testuser
        self.login('testuser')
        self.upload()
        self.logout()

        # try to delete as otheruser
        self.login('otheruser')
        rv = self.app.get('/lvfs/firmware/e133637179fa7c37d7a36657c7e302edce3d0fce/delete_force',
                          follow_redirects=True)
        assert b'Firmware deleted' not in rv.data, rv.data
        assert b'Insufficient permissions to delete firmware' in rv.data, rv.data

    def test_user_only_view_own_firmware(self):

        # create User:alice, User:bob, Analyst:clara, and QA:mario
        self.login()
        self.add_user('alice')
        self.add_user('bob')
        self.add_user('clara', is_analyst=True)
        self.add_user('mario', is_qa=True)
        self.logout()

        # let alice upload a file to embargo
        self.login('alice')
        self.upload('embargo')
        rv = self.app.get('/lvfs/firmware/e133637179fa7c37d7a36657c7e302edce3d0fce')
        assert b'/downloads/e133637179fa7c37d7a36657c7e302edce3d0fce' in rv.data, rv.data
        rv = self.app.get('/lvfs/firmware')
        assert b'e133637179fa7c37d7a36657c7e302edce3d0fce' in rv.data, rv.data
        rv = self.app.get('/lvfs/firmware/e133637179fa7c37d7a36657c7e302edce3d0fce/analytics/clients')
        assert b'Insufficient permissions to view analytics' in rv.data, rv.data
        self.logout()

        # bob can't see the file, nor can upload a duplicate
        self.login('bob')
        rv = self._upload('contrib/hughski-colorhug2-2.0.3.cab', 'embargo')
        assert b'Another user has already uploaded this firmware' in rv.data, rv.data
        rv = self.app.get('/lvfs/firmware/e133637179fa7c37d7a36657c7e302edce3d0fce')
        assert b'Insufficient permissions to view firmware' in rv.data, rv.data
        rv = self.app.get('/lvfs/firmware')
        assert b'No firmware has been uploaded yet' in rv.data, rv.data
        rv = self.app.get('/lvfs/firmware/e133637179fa7c37d7a36657c7e302edce3d0fce/analytics/clients')
        assert b'Insufficient permissions to view analytics' in rv.data, rv.data
        self.logout()

        # clara can see all firmwares, but can't promote them
        self.login('clara')
        rv = self.app.get('/lvfs/firmware/e133637179fa7c37d7a36657c7e302edce3d0fce')
        assert b'/downloads/e133637179fa7c37d7a36657c7e302edce3d0fce' in rv.data, rv.data
        rv = self.app.get('/lvfs/firmware')
        assert b'e133637179fa7c37d7a36657c7e302edce3d0fce' in rv.data, rv.data
        rv = self.app.get('/lvfs/firmware/e133637179fa7c37d7a36657c7e302edce3d0fce/analytics/clients')
        assert b'Recent Activity' in rv.data, rv.data
        rv = self.app.get('/lvfs/firmware/e133637179fa7c37d7a36657c7e302edce3d0fce/promote/testing',
                          follow_redirects=True)
        assert b'Permission denied: No QA access' in rv.data, rv.data
        self.logout()

        # mario can see things from both users and promote
        self.login('mario')
        rv = self.app.get('/lvfs/firmware/e133637179fa7c37d7a36657c7e302edce3d0fce')
        assert b'/downloads/e133637179fa7c37d7a36657c7e302edce3d0fce' in rv.data, rv.data
        rv = self.app.get('/lvfs/firmware')
        assert b'e133637179fa7c37d7a36657c7e302edce3d0fce' in rv.data, rv.data
        rv = self.app.get('/lvfs/firmware/e133637179fa7c37d7a36657c7e302edce3d0fce/analytics/clients')
        assert b'Recent Activity' in rv.data, rv.data
        rv = self.app.get('/lvfs/firmware/e133637179fa7c37d7a36657c7e302edce3d0fce/promote/testing',
                          follow_redirects=True)
        assert b'>testing<' in rv.data, rv.data
        self.logout()

    def test_eventlog(self):

        # login, upload then check both events were logged
        self.login()
        self.upload()
        rv = self.app.get('/lvfs/eventlog')
        assert b'Uploaded file' in rv.data, rv.data
        assert b'Logged on' in rv.data, rv.data
        assert b'>anonymous<' not in rv.data, rv.data

    def test_groups(self):

        # login then add group
        self.login()
        rv = self.app.post('/lvfs/group/add', data=dict(
            group_id='testgroup',
        ), follow_redirects=True)
        assert b'Added group' in rv.data, rv.data

        # add duplicate group
        rv = self.app.post('/lvfs/group/add', data=dict(
            group_id='testgroup',
        ), follow_redirects=True)
        assert b'Already a entry with that group' in rv.data, rv.data

        # get the grouplist
        rv = self.app.get('/lvfs/grouplist')
        assert b'testgroup' in rv.data, rv.data

        # add a vendor-id
        rv = self.app.get('/lvfs/group/testgroup/admin')
        assert b'Empty group' in rv.data, rv.data
        rv = self.app.post('/lvfs/group/testgroup/modify_by_admin',
                           data=dict(vendor_ids='USB:0x273F,PCI:0xBEEF'),
                           follow_redirects=True)
        assert b'USB:0x273F,PCI:0xBEEF' in rv.data, rv.data

        # delete the group
        rv = self.app.get('/lvfs/group/notgoingtoexist/delete', follow_redirects=True)
        assert b'No entry with group_id' in rv.data, rv.data
        rv = self.app.get('/lvfs/group/testgroup/delete', follow_redirects=True)
        assert b'Deleted group' in rv.data, rv.data

    def test_vendorlist(self):

        # check users can't modify the list
        rv = self.app.get('/lvfs/vendorlist')
        assert b'Create a new vendor' not in rv.data, rv.data

        # check admin can
        self.login()
        rv = self.app.get('/lvfs/vendorlist')
        assert b'Create a new vendor' in rv.data, rv.data

        # create new vendor
        rv = self.app.post('/lvfs/vendorlist/add', data=dict(group_id='testvendor'),
                           follow_redirects=True)
        assert b'Added vendor' in rv.data, rv.data
        rv = self.app.get('/lvfs/vendorlist')
        assert b'testvendor' in rv.data, rv.data

        # create duplicate
        rv = self.app.post('/lvfs/vendorlist/add', data=dict(group_id='testvendor'),
                           follow_redirects=True)
        assert b'Already a vendor with that group ID' in rv.data, rv.data

        # show the details page
        rv = self.app.get('/lvfs/vendor/testvendor/details')
        assert b'testvendor' in rv.data, rv.data

        # change some properties
        rv = self.app.post('/lvfs/vendor/testvendor/modify_by_admin', data=dict(
            display_name='VendorName',
            plugins='dfu 1.2.3',
            description='Everything supported',
            visible='1',
            is_fwupd_supported='1',
            is_account_holder='1',
            is_uploading='1',
            comments='Emailed Dave on 2018-01-14 to follow up.',
        ), follow_redirects=True)
        assert b'Updated vendor' in rv.data, rv.data
        rv = self.app.get('/lvfs/vendorlist')
        assert b'testvendor' in rv.data, rv.data
        assert b'Everything supported' in rv.data, rv.data
        assert b'Emailed Dave' not in rv.data, rv.data

        # delete
        rv = self.app.get('/lvfs/vendor/NOTGOINGTOEXIST/delete', follow_redirects=True)
        assert b'No a vendor with that group ID' in rv.data, rv.data
        rv = self.app.get('/lvfs/vendor/testvendor/delete', follow_redirects=True)
        assert b'Removed vendor' in rv.data, rv.data
        rv = self.app.get('/lvfs/vendorlist')
        assert b'testvendor' not in rv.data, rv.data

    def test_users(self):

        # login then add invalid users
        self.login()
        rv = self._add_user('testuser', 'testgroup', 'unsuitable', 'test@test.com')
        assert b'requires at least one uppercase character' in rv.data, rv.data
        rv = self._add_user('testuser', 'testgroup', 'Pa$$w0rd', 'testtestcom')
        assert b'Invalid email address' in rv.data, rv.data
        rv = self._add_user('XX', 'testgroup', 'Pa$$w0rd', 'test@test.com')
        assert b'Username invalid' in rv.data, rv.data
        rv = self._add_user('testuser', 'XX', 'Pa$$w0rd', 'test@test.com')
        assert b'QA group invalid' in rv.data, rv.data

        # add a good user, and check the user and group was created
        rv = self._add_user('testuser', 'testgroup', 'Pa$$w0rd', 'test@test.com')
        assert b'Added user' in rv.data, rv.data
        rv = self.app.get('/lvfs/userlist')
        assert b'testuser' in rv.data, rv.data
        rv = self.app.get('/lvfs/user/testuser/admin')
        assert b'test@test.com' in rv.data, rv.data
        rv = self.app.get('/lvfs/grouplist')
        assert b'testgroup' in rv.data, rv.data

        # modify an existing user as the admin
        rv = self.app.post('/lvfs/user/testuser/modify_by_admin', data=dict(
            is_enabled='1',
            is_qa='1',
            is_analyst='1',
            group_id='testgroup',
            display_name='Slightly Less Generic Name',
            email='test@test.com',
        ), follow_redirects=True)
        assert b'Updated profile' in rv.data, rv.data
        rv = self.app.get('/lvfs/user/testuser/admin')
        assert b'Slightly Less Generic Name' in rv.data, rv.data

        # ensure the user can log in
        self.logout()
        self.login('testuser')

        # ensure the user can change thier own password
        rv = self.app.post('/lvfs/user/testuser/modify', data=dict(
            password_old='not-even-close',
            password_new='Hi$$t0ry',
            name='Something Funky',
            email='test@test.com',
        ), follow_redirects=True)
        assert b'Incorrect existing password' in rv.data, rv.data
        rv = self.app.post('/lvfs/user/testuser/modify', data=dict(
            password_old='Pa$$w0rd',
            password_new='Hi$$t0ry',
            name='Something Funky',
            email='test@test.com',
        ), follow_redirects=True)
        assert b'Updated profile' in rv.data, rv.data
        rv = self.app.get('/lvfs/profile')
        assert b'Something Funky' in rv.data, rv.data
        assert b'test@test.com' in rv.data, rv.data

        # try to self-delete
        rv = self.app.get('/lvfs/user/testuser/delete')
        assert b'Unable to remove user as not admin' in rv.data, rv.data

        # delete the user as the admin
        self.logout()
        self.login()
        rv = self.app.get('/lvfs/user/testuser/delete', follow_redirects=True)
        assert b'Deleted user' in rv.data, rv.data
        rv = self.app.get('/lvfs/userlist')
        assert b'testuser' not in rv.data, rv.data

    def test_promote_as_user(self):

        # create User
        self.login()
        self.add_user('testuser')
        self.logout()

        # login as user, upload file, then promote
        self.login('testuser')
        self.upload()
        rv = self.app.get('/lvfs/firmware/e133637179fa7c37d7a36657c7e302edce3d0fce/promote/embargo',
                          follow_redirects=True)
        assert b'Moved firmware' in rv.data, rv.data
        assert b'>embargo<' in rv.data, rv.data
        rv = self.app.get('/lvfs/firmware/e133637179fa7c37d7a36657c7e302edce3d0fce/promote/embargo',
                          follow_redirects=True)
        assert b'Firmware already in that target' in rv.data, rv.data
        assert b'>embargo<' in rv.data, rv.data
        rv = self.app.get('/lvfs/firmware/e133637179fa7c37d7a36657c7e302edce3d0fce/promote/testing',
                          follow_redirects=True)
        assert b'Unable to promote as not QA' in rv.data, rv.data
        rv = self.app.get('/lvfs/firmware/e133637179fa7c37d7a36657c7e302edce3d0fce/promote/stable',
                          follow_redirects=True)
        assert b'Unable to promote as not QA' in rv.data, rv.data

        # demote back to private
        rv = self.app.get('/lvfs/firmware/e133637179fa7c37d7a36657c7e302edce3d0fce/promote/private',
                          follow_redirects=True)
        assert b'>private<' in rv.data, rv.data
        assert b'Moved firmware' in rv.data, rv.data

    def test_promote_as_qa(self):

        # login as user, upload file, then promote FIXME: do as QA user, not admin
        self.login()
        self.upload()
        rv = self.app.get('/lvfs/firmware/e133637179fa7c37d7a36657c7e302edce3d0fce/promote/embargo',
                          follow_redirects=True)
        assert b'Moved firmware' in rv.data, rv.data
        assert b'>embargo<' in rv.data, rv.data
        rv = self.app.get('/lvfs/firmware/e133637179fa7c37d7a36657c7e302edce3d0fce/promote/testing',
                          follow_redirects=True)
        assert b'Moved firmware' in rv.data, rv.data
        assert b'>testing<' in rv.data, rv.data
        rv = self.app.get('/lvfs/firmware/e133637179fa7c37d7a36657c7e302edce3d0fce/promote/stable',
                          follow_redirects=True)
        assert b'Moved firmware' in rv.data, rv.data
        assert b'>stable<' in rv.data, rv.data

        # demote back to testing then private
        rv = self.app.get('/lvfs/firmware/e133637179fa7c37d7a36657c7e302edce3d0fce/promote/testing',
                          follow_redirects=True)
        assert b'Moved firmware' in rv.data, rv.data
        assert b'>testing<' in rv.data, rv.data
        rv = self.app.get('/lvfs/firmware/e133637179fa7c37d7a36657c7e302edce3d0fce/promote/private',
                          follow_redirects=True)
        assert b'Moved firmware' in rv.data, rv.data
        assert b'>private<' in rv.data, rv.data

    def _report(self, updatestate=2, checksum='93496305fe2c9997aa7a3e3cbb8b96b9a0c1d325'):
        return self.app.post('/lvfs/firmware/report', data=
                             '{'
                             '  "ReportVersion" : 2,'
                             '  "MachineId" : "abc",'
                             '  "Metadata" : {'
                             '    "DistroId" : "fedora",'
                             '    "DistroVersion" : "27",'
                             '    "DistroVariant" : "workstation"'
                             '  },'
                             '  "Reports" : ['
                             '    {'
                             '      "Checksum" : "%s",'
                             '      "UpdateState" : %i,'
                             '      "Guid" : "e133637179fa7c37d7a36657c7e302edce3d0fce",'
                             '      "Plugin" : "colorhug",'
                             '      "VersionOld" : "2.0.0",'
                             '      "VersionNew" : "2.0.3",'
                             '      "Flags" : 34,'
                             '      "Created" : 1518212684,'
                             '      "Modified" : 1518212754,'
                             '      "Metadata" : {'
                             '        "AppstreamGlibVersion" : "0.7.5",'
                             '        "CpuArchitecture" : "x86_64",'
                             '        "FwupdVersion" : "1.0.5",'
                             '        "GUsbVersion" : "0.2.11",'
                             '        "BootTime" : "1518082325",'
                             '        "KernelVersion" : "4.14.16-300.fc27.x86_64"'
                             '      }'
                             '    }'
                             '  ]'
                             '}' % (checksum, updatestate))

    def test_reports(self):

        # upload a firmware that can receive a report
        self.login()
        self.upload(target='stable')

        # send empty
        rv = self.app.post('/lvfs/firmware/report')
        assert b'No JSON object could be decoded' in rv.data, rv.data

        # self less than what we need
        rv = self.app.post('/lvfs/firmware/report', data='{"MachineId" : "abc"}')
        assert b'invalid data, expected ReportVersion' in rv.data, rv.data

        # send a valid report for firmware that is not known to us
        rv = self._report(checksum='c0243a8553f19d3c405004d3642d1485a723c948')
        assert b'c0243a8553f19d3c405004d3642d1485a723c948 did not match any known firmware archive' in rv.data, rv.data

        # send a valid report for firmware that is known
        rv = self._report(updatestate=3)
        assert b'"success": true' in rv.data, rv.data
        assert b'replaces old report' not in rv.data, rv.data

        # send an update
        rv = self._report()
        assert b'"success": true' in rv.data, rv.data
        assert b'replaces old report' in rv.data, rv.data

        # get a report that does not exist
        rv = self.app.get('/lvfs/report/123456')
        assert b'Report does not exist' in rv.data, rv.data

        # check the saved report
        rv = self.app.get('/lvfs/report/0')
        assert b'"UpdateState": 2' in rv.data, rv.data

        # check the report appeared on the telemetry page
        rv = self.app.get('/lvfs/telemetry')
        assert b'ColorHug2 Device Update' in rv.data, rv.data
        assert b'>1<' in rv.data, rv.data

        # delete the report
        rv = self.app.get('/lvfs/report/0/delete', follow_redirects=True)
        assert b'Deleted report' in rv.data, rv.data

        # check it is really deleted
        rv = self.app.get('/lvfs/report/0')
        assert b'Report does not exist' in rv.data, rv.data

    def test_settings(self):

        # open the main page
        self.login()
        rv = self.app.get('/lvfs/settings')
        assert b'General server settings' in rv.data, rv.data
        assert b'Windows Update' in rv.data, rv.data

        # dig into the Windows Update page
        rv = self.app.get('/lvfs/settings/wu-copy')
        assert b'Copy files generated' in rv.data, rv.data
        assert b'value="enabled" checked>' in rv.data, rv.data

        # change both values to False
        rv = self.app.post('/lvfs/settings/modify/wu-copy', data=dict(
            wu_copy_inf='disabled',
            wu_copy_cat='disabled',
        ), follow_redirects=True)
        assert b'Copy files generated' in rv.data, rv.data
        assert b'value="enabled">' in rv.data, rv.data

        # and back to True
        rv = self.app.post('/lvfs/settings/modify/wu-copy', data=dict(
            wu_copy_inf='enabled',
            wu_copy_cat='enabled',
        ), follow_redirects=True)
        assert b'value="enabled" checked>' in rv.data, rv.data

    def test_updateinfo(self):

        # get the default update info from the firmware archive
        self.login()
        self.upload()
        rv = self.app.get('/lvfs/component/1/update')
        assert b'Work around the MCDC04 errata' in rv.data, rv.data
        assert b'value="low" selected' in rv.data, rv.data

        # edit the description and severity
        rv = self.app.post('/lvfs/firmware/e133637179fa7c37d7a36657c7e302edce3d0fce/modify', data=dict(
            urgency='critical',
            description='Not enough cats!',
        ), follow_redirects=True)
        assert b'Update text edited successfully' in rv.data, rv.data

        # verify the new update info
        rv = self.app.get('/lvfs/component/1/update')
        assert b'Not enough cats' in rv.data, rv.data
        assert b'value="critical" selected' in rv.data, rv.data

    def test_requires(self):

        # check existing requires were added
        self.login()
        self.app.get('/lvfs/component/requirement/repair')
        self.upload()

        # check requirements were copied out from the .metainfo.xml file
        rv = self.app.get('/lvfs/component/1/requires')
        assert b'85d38fda-fc0e-5c6f-808f-076984ae7978' in rv.data, rv.data
        assert b'name="version" value="1.0.3' in rv.data, rv.data
        assert b'ge" selected' in rv.data, rv.data
        assert b'regex" selected' in rv.data, rv.data
        assert b'BOT03.0[2-9]_*' in rv.data, rv.data

        # remove the CHID requirement
        rv = self.app.get('/lvfs/component/requirement/delete/3', follow_redirects=True)
        assert b'Removed requirement' in rv.data, rv.data
        assert b'85d38fda-fc0e-5c6f-808f-076984ae7978' not in rv.data, rv.data

        # add an invalid CHID
        rv = self.app.post('/lvfs/component/requirement/add', data=dict(
            component_id='1',
            kind='hardware',
            value='NOVALIDGUID',
        ), follow_redirects=True)
        assert b'NOVALIDGUID was not a valid GUID' in rv.data, rv.data

        # add a valid CHID
        rv = self.app.post('/lvfs/component/requirement/add', data=dict(
            component_id='1',
            kind='hardware',
            value='85d38fda-fc0e-5c6f-808f-076984ae7978',
        ), follow_redirects=True)
        assert b'85d38fda-fc0e-5c6f-808f-076984ae7978' in rv.data, rv.data
        assert b'Added requirement' in rv.data, rv.data

        # modify an existing requirement by adding it again
        rv = self.app.post('/lvfs/component/requirement/add', data=dict(
            component_id='1',
            kind='id',
            value='org.freedesktop.fwupd',
            compare='ge',
            version='1.0.4',
        ), follow_redirects=True)
        assert b'name="version" value="1.0.4' in rv.data, rv.data
        assert b'Modified requirement' in rv.data, rv.data

        # delete a requirement by adding an 'any' comparison
        rv = self.app.post('/lvfs/component/requirement/add', data=dict(
            component_id='1',
            kind='id',
            value='org.freedesktop.fwupd',
            compare='any',
            version='1.0.4',
        ), follow_redirects=True)
        assert b'name="version" value="1.0.4' not in rv.data, rv.data
        assert b'Deleted requirement' in rv.data, rv.data

    def test_metadata_rebuild(self):

        # create ODM user as admin
        self.login()
        self.add_user('testuser')
        self.logout()

        # login and upload firmware to embargo
        self.login('testuser')
        self.upload(target='embargo')

        # relogin as admin and rebuild metadata
        self.logout()
        self.login()
        rv = self.app.get('/lvfs/metadata/rebuild', follow_redirects=True)
        assert b'Metadata rebuilt successfully' in rv.data, rv.data

        # check the remote is generated
        rv = self.app.get('/lvfs/metadata/testgroup')
        assert b'Title=Embargoed for testgroup' in rv.data, rv.data

    def test_nologin_required(self):

        # all these are viewable without being logged in
        uris = ['/',
                '/lvfs',
                '/vendors',
                '/users',
                '/developers',
                '/privacy',
                '/status',
                '/donations',
                '/vendorlist',
                '/lvfs/newaccount',
                '/lvfs/devicelist',
                '/lvfs/device/2082b5e0-7a64-478a-b1b2-e3404fab6dad',
               ]
        for uri in uris:
            print('GET', uri)
            rv = self.app.get(uri, follow_redirects=True)
            assert b'favicon.ico' in rv.data, rv.data
            assert b'LVFS: Error' not in rv.data, rv.data

    def test_fail_when_login_required(self):

        # all these are an error when not logged in
        uris = ['/lvfs/firmware']
        for uri in uris:
            print('GET', uri)
            rv = self.app.get(uri)
            assert b'favicon.ico' in rv.data, rv.data
            assert b'LVFS: Error' in rv.data, rv.data

if __name__ == '__main__':
    unittest.main()
