#!/usr/bin/python2
# -*- coding: utf-8 -*-
#
# Copyright (C) 2018 Richard Hughes <richard@hughsie.com>
# Licensed under the GNU General Public License Version 2
#
# pylint: disable=fixme,too-many-public-methods,line-too-long

from __future__ import print_function

import os
import unittest
import tempfile
import subprocess

class LvfsTestCase(unittest.TestCase):

    def setUp(self):

        # create new database
        self.db_fd, self.db_filename = tempfile.mkstemp()
        self.db_uri = 'sqlite:///' + self.db_filename

        # write out custom settings file
        self.cfg_fd, self.cfg_filename = tempfile.mkstemp()
        cfgfile = open(self.cfg_filename, 'w')
        cfgfile.write('\n'.join([
            "SQLALCHEMY_DATABASE_URI = '%s'" % self.db_uri,
            "DOWNLOAD_DIR = '/tmp'",
            ]))
        cfgfile.close()

        # create instance
        import app as lvfs
        from app import db
        from app.dbutils import init_db
        self.app = lvfs.app.test_client()
        lvfs.app.config.from_pyfile(self.cfg_filename)
        with lvfs.app.app_context():
            init_db(db)

        # ensure the plugins settings are set up
        self.login()
        self.app.get('/lvfs/settings_create')
        self.logout()

    def tearDown(self):
        os.close(self.db_fd)
        os.unlink(self.db_filename)
        os.close(self.cfg_fd)
        os.unlink(self.cfg_filename)

    def _login(self, username, password):
        return self.app.post('/lvfs/login', data=dict(
            username=username,
            password=password
        ), follow_redirects=True)

    def _logout(self):
        return self.app.get('/lvfs/logout', follow_redirects=True)

    def login(self, username='sign-test@fwupd.org', password=u'Pa$$w0rd'):
        rv = self._login(username, password)
        assert b'/lvfs/upload' in rv.data, rv.data
        assert b'Incorrect username or password' not in rv.data, rv.data

    def logout(self):
        rv = self._logout()
        assert b'Logged out' in rv.data, rv.data
        assert b'/lvfs/upload' not in rv.data, rv.data

    def delete_firmware(self, firmware_id=1):
        rv = self.app.get('/lvfs/firmware/%i/delete' % firmware_id,
                          follow_redirects=True)
        assert b'Firmware deleted' in rv.data, rv.data

    def _add_user(self, username, group_id, password):
        return self.app.post('/lvfs/user/add', data=dict(
            username=username,
            password_new=password,
            group_id=group_id,
            display_name=u'Generic Name',
        ), follow_redirects=True)

    def add_user(self, username='testuser@fwupd.org', group_id='testgroup',
                 password=u'Pa$$w0rd', is_qa=False, is_analyst=False):
        rv = self._add_user(username, group_id, password)
        assert b'Added user' in rv.data, rv.data
        user_id_idx = rv.data.find('Added user ')
        assert user_id_idx != -1, rv.data
        user_id = int(rv.data[user_id_idx+11:user_id_idx+12])
        assert user_id != 0, rv.data
        if is_qa or is_analyst:
            data = {'auth_type': 'local'}
            if is_qa:
                data['is_qa'] = '1'
            if is_analyst:
                data['is_analyst'] = '1'
            rv = self.app.post('/lvfs/user/%i/modify_by_admin' % user_id,
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
        assert b'Uploaded file' in rv.data, rv.data
        assert b'7514fc4b0e1a306337de78c58f10e9e68f791de2' in rv.data, rv.data

    def test_login_logout(self):

        # test logging in and out
        rv = self._login('sign-test@fwupd.org', u'Pa$$w0rd')
        assert b'/lvfs/upload' in rv.data, rv.data
        rv = self._logout()
        rv = self._login('sign-test@fwupd.org', u'Pa$$w0rd')
        assert b'/lvfs/upload' in rv.data, rv.data
        rv = self._logout()
        assert b'/lvfs/upload' not in rv.data, rv.data
        rv = self._login('sign-test@fwupd.orgx', u'default')
        assert b'Incorrect username or password' in rv.data, rv.data
        rv = self._login('sign-test@fwupd.org', u'defaultx')
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
        assert b'7514fc4b0e1a306337de78c58f10e9e68f791de2' in rv.data, rv.data
        rv = self.app.get('/lvfs/firmware/1/components')
        assert b'com.hughski.ColorHug2.firmware' in rv.data, rv.data

        # download
        rv = self.app.get('/downloads/7514fc4b0e1a306337de78c58f10e9e68f791de2-hughski-colorhug2-2.0.3.cab')
        assert rv.status_code == 200, rv.status_code
        assert len(rv.data) == 10974, len(rv.data)

        # check analytics works
        uris = ['/lvfs/firmware/1/analytics',
                '/lvfs/firmware/1/analytics/clients',
                '/lvfs/firmware/1/analytics/month',
                '/lvfs/firmware/1/analytics/reports',
                '/lvfs/firmware/1/analytics/year']
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
        rv = self.app.get('/lvfs/firmware/1/promote/testing',
                          follow_redirects=True)
        assert b'>testing<' in rv.data, rv.data
        assert b'>stable<' not in rv.data, rv.data
        rv = self.app.get('/lvfs/firmware/1/promote/stable',
                          follow_redirects=True)
        assert b'>stable<' in rv.data, rv.data

        # check it's now in the devicelist as anon
        self.logout()
        rv = self.app.get('/lvfs/devicelist')
        assert b'ColorHug' in rv.data, rv.data
        self.login()

        # download it
        rv = self.app.get('/downloads/7514fc4b0e1a306337de78c58f10e9e68f791de2-hughski-colorhug2-2.0.3.cab')
        assert rv.status_code == 200, rv.status_code

        # test deleting the firmware
        self.delete_firmware()

        # download missing file
        rv = self.app.get('/downloads/7514fc4b0e1a306337de78c58f10e9e68f791de2-hughski-colorhug2-2.0.3.cab')
        assert rv.status_code == 404, rv.status_code

    def test_user_delete_wrong_user(self):

        # create user
        self.login()
        self.add_user('testuser@fwupd.org')
        self.add_user('otheruser@fwupd.org')
        self.logout()

        # upload as testuser
        self.login('testuser@fwupd.org')
        self.upload()
        self.logout()

        # try to delete as otheruser
        self.login('otheruser@fwupd.org')
        rv = self.app.get('/lvfs/firmware/1/delete',
                          follow_redirects=True)
        assert b'Firmware deleted' not in rv.data, rv.data
        assert b'Insufficient permissions to delete firmware' in rv.data, rv.data

    def test_user_delete_qa_wrong_group(self):

        # create user
        self.login()
        self.add_user('testuser@fwupd.org')
        self.add_user('otheruser@fwupd.org', 'different_group', is_qa=True)
        self.logout()

        # upload as testuser
        self.login('testuser@fwupd.org')
        self.upload()
        self.logout()

        # try to delete as otheruser
        self.login('otheruser@fwupd.org')
        rv = self.app.get('/lvfs/firmware/1/delete',
                          follow_redirects=True)
        assert b'Firmware deleted' not in rv.data, rv.data
        assert b'Insufficient permissions to delete firmware' in rv.data, rv.data

    def test_cron_metadata(self):

        # verify all metadata is in good shape
        self.login()
        rv = self.app.get('/lvfs/metadata')
        assert b'Will be signed in' not in rv.data, rv.data

        # upload file, dirtying the admin-embargo remote
        self.upload('embargo')
        rv = self.app.get('/lvfs/metadata')
        assert b'Will be signed in' in rv.data, rv.data

        # run the cron job manually
        env = {}
        env['LVFS_CUSTOM_SETTINGS'] = self.cfg_filename
        ps = subprocess.Popen(['./cron.py', 'metadata'], env=env,
                              stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE)
        stdout, _ = ps.communicate()
        assert 'Updating: embargo-admin' in stdout, stdout

        # verify all metadata is in good shape
        rv = self.app.get('/lvfs/metadata')
        assert b'Will be signed in' not in rv.data, rv.data

    def test_cron_firmware(self):

        # upload file, which will be unsigned
        self.login()
        self.upload('embargo')
        rv = self.app.get('/lvfs/firmware/1')
        assert b'>Signed<' not in rv.data, rv.data
        rv = self.app.get('/lvfs/firmware/1/problems')
        assert b'Firmware is unsigned' in rv.data, rv.data

        # run the cron job manually
        env = {}
        env['LVFS_CUSTOM_SETTINGS'] = self.cfg_filename
        ps = subprocess.Popen(['./cron.py', 'firmware'], env=env,
                              stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE)
        stdout, _ = ps.communicate()
        assert 'Signing: /tmp/7514fc4b0e1a306337de78c58f10e9e68f791de2-hughski-colorhug2-2.0.3.cab' in stdout, stdout

        # verify the firmware is now signed
        rv = self.app.get('/lvfs/firmware/1')
        assert b'>Signed<' in rv.data, rv.data
        rv = self.app.get('/lvfs/firmware/1/problems')
        assert b'Firmware is unsigned' not in rv.data, rv.data

    def test_user_only_view_own_firmware(self):

        # create User:alice, User:bob, Analyst:clara, and QA:mario
        self.login()
        self.add_user('alice@fwupd.org')
        self.add_user('bob@fwupd.org')
        self.add_user('clara@fwupd.org', is_analyst=True)
        self.add_user('mario@fwupd.org', is_qa=True)
        self.logout()

        # let alice upload a file to embargo
        self.login('alice@fwupd.org')
        self.upload('embargo')
        rv = self.app.get('/lvfs/firmware/1')
        assert b'/downloads/7514fc4b0e1a306337de78c58f10e9e68f791de2' in rv.data, rv.data
        rv = self.app.get('/lvfs/firmware')
        assert b'/lvfs/firmware/1' in rv.data, rv.data
        rv = self.app.get('/lvfs/firmware/1/analytics/clients')
        assert b'Insufficient permissions to view analytics' in rv.data, rv.data
        self.logout()

        # bob can't see the file, nor can upload a duplicate
        self.login('bob@fwupd.org')
        rv = self._upload('contrib/hughski-colorhug2-2.0.3.cab', 'embargo')
        assert b'Another user has already uploaded this firmware' in rv.data, rv.data
        rv = self.app.get('/lvfs/firmware/1')
        assert b'Insufficient permissions to view firmware' in rv.data, rv.data
        rv = self.app.get('/lvfs/firmware')
        assert b'No firmware has been uploaded' in rv.data, rv.data
        rv = self.app.get('/lvfs/firmware/1/analytics/clients')
        assert b'Insufficient permissions to view analytics' in rv.data, rv.data
        self.logout()

        # clara can see all firmwares, but can't promote them
        self.login('clara@fwupd.org')
        rv = self.app.get('/lvfs/firmware/1')
        assert b'/downloads/7514fc4b0e1a306337de78c58f10e9e68f791de2' in rv.data, rv.data
        rv = self.app.get('/lvfs/firmware')
        assert b'/lvfs/firmware/1' in rv.data, rv.data
        rv = self.app.get('/lvfs/firmware/1/analytics/clients')
        assert b'User Agent' in rv.data, rv.data
        rv = self.app.get('/lvfs/firmware/1/promote/testing',
                          follow_redirects=True)
        assert b'Permission denied: No QA access' in rv.data, rv.data
        self.logout()

        # mario can see things from both users and promote
        self.login('mario@fwupd.org')
        rv = self.app.get('/lvfs/firmware/1')
        assert b'/downloads/7514fc4b0e1a306337de78c58f10e9e68f791de2' in rv.data, rv.data
        rv = self.app.get('/lvfs/firmware')
        assert b'/lvfs/firmware/1' in rv.data, rv.data
        rv = self.app.get('/lvfs/firmware/1/analytics/clients')
        assert b'User Agent' in rv.data, rv.data
        rv = self.app.get('/lvfs/firmware/1/promote/testing',
                          follow_redirects=True)
        assert b'>testing<' in rv.data, rv.data
        self.logout()

    def test_eventlog(self):

        # login, upload then check both events were logged
        self.login()
        self.upload()
        rv = self.app.get('/lvfs/eventlog')
        assert b'Uploaded file' in rv.data, rv.data
        assert b'Logged in' in rv.data, rv.data
        assert b'>anonymous<' not in rv.data, rv.data

    def test_vendorlist(self):

        # check users can't modify the list
        rv = self.app.get('/lvfs/vendorlist')
        assert b'Create a new vendor' not in rv.data, rv.data

        # check admin can
        self.login()
        rv = self.app.get('/lvfs/vendorlist')
        assert b'Create a new vendor' in rv.data, rv.data

        # create new vendor
        rv = self.app.post('/lvfs/vendor/add', data=dict(group_id='testvendor'),
                           follow_redirects=True)
        assert b'Added vendor' in rv.data, rv.data
        rv = self.app.get('/lvfs/vendorlist')
        assert b'testvendor' in rv.data, rv.data

        # create duplicate
        rv = self.app.post('/lvfs/vendor/add', data=dict(group_id='testvendor'),
                           follow_redirects=True)
        assert b'Group ID already exists' in rv.data, rv.data

        # show the details page
        rv = self.app.get('/lvfs/vendor/2/details')
        assert b'testvendor' in rv.data, rv.data

        # create a restriction
        rv = self.app.post('/lvfs/vendor/2/restriction/add', data=dict(value='USB:0x1234'),
                           follow_redirects=True)
        assert b'Added restriction' in rv.data, rv.data

        # show the restrictions page
        rv = self.app.get('/lvfs/vendor/2/restrictions')
        assert b'USB:0x1234' in rv.data, rv.data

        # delete a restriction
        rv = self.app.get('/lvfs/vendor/2/restriction/1/delete', follow_redirects=True)
        assert b'Deleted restriction' in rv.data, rv.data
        assert b'USB:0x1234' not in rv.data, rv.data

        # change some properties
        rv = self.app.post('/lvfs/vendor/2/modify_by_admin', data=dict(
            display_name='VendorName',
            plugins='dfu 1.2.3',
            description='Everything supported',
            visible=True,
            is_fwupd_supported='1',
            is_account_holder='1',
            is_uploading='1',
            keywords='keyword',
            comments='Emailed Dave on 2018-01-14 to follow up.',
        ), follow_redirects=True)
        assert b'Updated vendor' in rv.data, rv.data
        rv = self.app.get('/lvfs/vendorlist')
        assert b'testvendor' in rv.data, rv.data
        assert b'Everything supported' in rv.data, rv.data
        assert b'Emailed Dave' not in rv.data, rv.data

        # delete
        rv = self.app.get('/lvfs/vendor/999/delete', follow_redirects=True)
        assert b'No a vendor with that group ID' in rv.data, rv.data
        rv = self.app.get('/lvfs/vendor/2/delete', follow_redirects=True)
        assert b'Removed vendor' in rv.data, rv.data
        rv = self.app.get('/lvfs/vendorlist')
        assert b'testvendor' not in rv.data, rv.data

    def test_users(self):

        # login then add invalid users
        self.login()
        rv = self._add_user('testuser@fwupd.org', 'testgroup', u'unsuitable')
        assert b'requires at least one uppercase character' in rv.data, rv.data
        rv = self._add_user('testuser', 'testgroup', u'Pa$$w0rd')
        assert b'Invalid email address' in rv.data, rv.data
        rv = self._add_user('testuser@fwupd.org', 'XX', u'Pa$$w0rd')
        assert b'QA group invalid' in rv.data, rv.data

        # add a good user, and check the user and group was created
        rv = self._add_user('testuser@fwupd.org', 'testgroup', u'Pa$$w0rd')
        assert b'Added user' in rv.data, rv.data
        rv = self.app.get('/lvfs/userlist')
        assert b'testuser' in rv.data, rv.data
        rv = self.app.get('/lvfs/user/3/admin')
        assert b'testuser@fwupd.org' in rv.data, rv.data
        rv = self.app.get('/lvfs/vendorlist')
        assert b'testgroup' in rv.data, rv.data

        # modify an existing user as the admin
        rv = self.app.post('/lvfs/user/3/modify_by_admin', data=dict(
            auth_type='auth_type',
            is_qa='1',
            is_analyst='1',
            group_id='testgroup',
            display_name='Slightly Less Generic Name',
        ), follow_redirects=True)
        assert b'Updated profile' in rv.data, rv.data
        rv = self.app.get('/lvfs/user/3/admin')
        assert b'Slightly Less Generic Name' in rv.data, rv.data

        # ensure the user can log in
        self.logout()
        self.login('testuser@fwupd.org')

        # ensure the user can change thier own password
        rv = self.app.post('/lvfs/user/3/modify', data=dict(
            password_old=u'not-even-close',
            password_new=u'Hi$$t0ry',
            display_name=u'Something Funky',
        ), follow_redirects=True)
        assert b'Incorrect existing password' in rv.data, rv.data
        rv = self.app.post('/lvfs/user/3/modify', data=dict(
            password_old=u'Pa$$w0rd',
            password_new=u'Hi$$t0ry',
            display_name=u'Something Funky',
        ), follow_redirects=True)
        assert b'Updated profile' in rv.data, rv.data
        rv = self.app.get('/lvfs/profile')
        assert b'Something Funky' in rv.data, rv.data

        # try to self-delete
        rv = self.app.get('/lvfs/user/3/delete')
        assert b'Unable to remove user as not admin' in rv.data, rv.data

        # delete the user as the admin
        self.logout()
        self.login()
        rv = self.app.get('/lvfs/user/3/delete', follow_redirects=True)
        assert b'Deleted user' in rv.data, rv.data
        rv = self.app.get('/lvfs/userlist')
        assert b'testuser@fwupd.org' not in rv.data, rv.data

    def test_promote_as_user(self):

        # create User
        self.login()
        self.add_user('testuser@fwupd.org')
        self.logout()

        # login as user, upload file, then promote
        self.login('testuser@fwupd.org')
        self.upload()
        rv = self.app.get('/lvfs/firmware/1/promote/embargo',
                          follow_redirects=True)
        assert b'Moved firmware' in rv.data, rv.data
        assert b'>embargo-testgroup<' in rv.data, rv.data
        rv = self.app.get('/lvfs/firmware/1/promote/embargo',
                          follow_redirects=True)
        assert b'Firmware already in that target' in rv.data, rv.data
        assert b'>embargo-testgroup<' in rv.data, rv.data
        rv = self.app.get('/lvfs/firmware/1/promote/testing',
                          follow_redirects=True)
        assert b'Unable to promote as not QA' in rv.data, rv.data
        rv = self.app.get('/lvfs/firmware/1/promote/stable',
                          follow_redirects=True)
        assert b'Unable to promote as not QA' in rv.data, rv.data

        # demote back to private
        rv = self.app.get('/lvfs/firmware/1/promote/private',
                          follow_redirects=True)
        assert b'>private<' in rv.data, rv.data
        assert b'Moved firmware' in rv.data, rv.data

    def test_promote_as_qa(self):

        # login as user, upload file, then promote FIXME: do as QA user, not admin
        self.login()
        self.upload()
        rv = self.app.get('/lvfs/firmware/1/promote/embargo',
                          follow_redirects=True)
        assert b'Moved firmware' in rv.data, rv.data
        assert b'>embargo-admin<' in rv.data, rv.data
        rv = self.app.get('/lvfs/firmware/1/promote/testing',
                          follow_redirects=True)
        assert b'Moved firmware' in rv.data, rv.data
        assert b'>testing<' in rv.data, rv.data
        rv = self.app.get('/lvfs/firmware/1/promote/stable',
                          follow_redirects=True)
        assert b'Moved firmware' in rv.data, rv.data
        assert b'>stable<' in rv.data, rv.data

        # demote back to testing then private
        rv = self.app.get('/lvfs/firmware/1/promote/testing',
                          follow_redirects=True)
        assert b'Moved firmware' in rv.data, rv.data
        assert b'>testing<' in rv.data, rv.data
        rv = self.app.get('/lvfs/firmware/1/promote/private',
                          follow_redirects=True)
        assert b'Moved firmware' in rv.data, rv.data
        assert b'>private<' in rv.data, rv.data

    def _report(self, updatestate=2, distro_id='fedora', checksum='3f1b8ec0fa8ee323d1934a0256037c8100175755'):
        return self.app.post('/lvfs/firmware/report', data=
                             '{'
                             '  "ReportVersion" : 2,'
                             '  "MachineId" : "abc",'
                             '  "Metadata" : {'
                             '    "DistroId" : "%s",'
                             '    "DistroVersion" : "27",'
                             '    "DistroVariant" : "workstation"'
                             '  },'
                             '  "Reports" : ['
                             '    {'
                             '      "Checksum" : "%s",'
                             '      "UpdateState" : %i,'
                             '      "UpdateError" : "UEFI firmware update failed: failed to make /boot/efi/EFI/arch/fw: No such file or directory",'
                             '      "Guid" : "7514fc4b0e1a306337de78c58f10e9e68f791de2",'
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
                             '}' % (distro_id, checksum, updatestate))

    def test_reports(self):

        # upload a firmware that can receive a report
        self.login()
        self.upload(target='testing')

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
        rv = self.app.get('/lvfs/report/1')
        assert b'UpdateState=success' in rv.data, rv.data

        # check the report appeared on the telemetry page
        rv = self.app.get('/lvfs/telemetry')
        assert b'ColorHug2 Device Update' in rv.data, rv.data
        assert b'>1<' in rv.data, rv.data

        # delete the report
        rv = self.app.get('/lvfs/report/1/delete', follow_redirects=True)
        assert b'Deleted report' in rv.data, rv.data

        # check it is really deleted
        rv = self.app.get('/lvfs/report/1')
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
        rv = self.app.post('/lvfs/firmware/1/modify', data=dict(
            urgency='critical',
            description=u'Not enough cats!',
        ), follow_redirects=True)
        assert b'Update text updated' in rv.data, rv.data

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
        assert b'Removed requirement 85d38fda-fc0e-5c6f-808f-076984ae7978' in rv.data, rv.data

        # add an invalid CHID
        rv = self.app.post('/lvfs/component/requirement/add', data=dict(
            component_id='1',
            kind='hardware',
            value='NOVALIDGUID',
        ), follow_redirects=True)
        assert b'NOVALIDGUID is not a valid GUID' in rv.data, rv.data

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

    def test_keywords(self):

        # upload file with keywords
        self.login()
        self.upload()

        # check keywords were copied out from the .metainfo.xml file
        rv = self.app.get('/lvfs/component/1/keywords')
        assert b'>alice<' in rv.data, rv.data
        assert b'>bob<' in rv.data, rv.data

        # add another set of keywords
        rv = self.app.post('/lvfs/component/keyword/add', data=dict(
            component_id='1',
            value='Clara Dave',
        ), follow_redirects=True)
        assert b'Added keywords' in rv.data, rv.data
        assert b'>clara<' in rv.data, rv.data
        assert b'>dave<' in rv.data, rv.data

        # delete one of the added keywords
        rv = self.app.get('/lvfs/component/keyword/5/delete', follow_redirects=True)
        assert b'Removed keyword' in rv.data, rv.data
        assert b'>alice<' in rv.data, rv.data
        assert b'>colorimeter<' not in rv.data, rv.data

    def test_anon_search(self):

        # upload file with keywords
        self.login()
        self.upload(target='testing')
        self.logout()

        # search for something that does not exist
        rv = self.app.get('/lvfs/search?value=Edward')
        assert b'No results found for' in rv.data, rv.data

        # search for one defined keyword
        rv = self.app.get('/lvfs/search?value=Alice')
        assert b'ColorHug2 Device Update' in rv.data, rv.data

        # search for one defined keyword, again
        rv = self.app.get('/lvfs/search?value=Alice')
        assert b'ColorHug2 Device Update' in rv.data, rv.data

        # search for a keyword and a name match
        rv = self.app.get('/lvfs/search?value=Alice+Edward+ColorHug2')
        assert b'ColorHug2 Device Update' in rv.data, rv.data

    def test_anon_search_not_promoted(self):

        # upload file with keywords
        self.login()
        self.upload(target='embargo')
        self.logout()

        # search for something that does not exist
        rv = self.app.get('/lvfs/search?value=alice')
        assert b'No results found for' in rv.data, rv.data

    def test_metadata_rebuild(self):

        # create ODM user as admin
        self.login()
        self.add_user('testuser@fwupd.org')
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
            rv = self.app.get(uri, follow_redirects=True)
            assert b'favicon.ico' in rv.data, rv.data
            assert b'LVFS: Error' not in rv.data, rv.data

    def test_fail_when_login_required(self):

        # all these are an error when not logged in
        uris = ['/lvfs/firmware']
        for uri in uris:
            rv = self.app.get(uri)
            assert b'favicon.ico' in rv.data, rv.data
            assert b'LVFS: Error' in rv.data, rv.data

    def add_issue(self, issue_id=1, url='https://github.com/hughsie/fwupd/wiki/Arch-Linux', name='ColorHug on Fedora'):

        # create an issue
        rv = self.app.post('/lvfs/issue/add', data=dict(
            url=url,
        ), follow_redirects=True)
        assert b'Added issue' in rv.data, rv.data
        rv = self.app.get('/lvfs/issue/all')
        assert url in rv.data, rv.data
        rv = self.app.get('/lvfs/issue/%i/details' % issue_id, follow_redirects=True)
        assert url in rv.data, rv.data

        # modify the description
        data = {'name': name,
                'description': 'Matches updating ColorHug on Fedora'}
        rv = self.app.post('/lvfs/issue/%i/modify' % issue_id, data=data, follow_redirects=True)
        assert name in rv.data, rv.data
        assert b'Matches updating ColorHug on Fedora' in rv.data, rv.data

    def _enable_issue(self, issue_id=1):
        return self.app.post('/lvfs/issue/%i/modify' % issue_id, data=dict(
            enabled=True,
        ), follow_redirects=True)

    def enable_issue(self, issue_id=1):
        rv = self._enable_issue(issue_id)
        assert b'Modified issue' in rv.data, rv.data

    def _add_issue_condition(self, issue_id=1, key='DistroId', value='fedora', compare='eq'):
        data = {
            'key': key,
            'value': value,
            'compare': compare,
        }
        return self.app.post('/lvfs/issue/%i/condition/add' % issue_id,
                             data=data, follow_redirects=True)

    def add_issue_condition(self, issue_id=1):
        rv = self._add_issue_condition(issue_id)
        assert b'Added condition' in rv.data, rv.data

    def test_issues_as_admin(self):

        # login, and check there are no issues
        self.login()
        rv = self.app.get('/lvfs/issue/all')
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
        assert b'https://github.com/hughsie/fwupd/wiki/Arch-Linux' in rv.data, rv.data

        # add a report not matching the issue
        rv = self._report(updatestate=3, distro_id='rhel')
        assert b'The failure is a known issue' not in rv.data, rv.data
        assert b'https://github.com/hughsie/fwupd/wiki/Arch-Linux' not in rv.data, rv.data

        # remove Condition
        rv = self.app.get('/lvfs/issue/1/condition/1/delete', follow_redirects=True)
        assert b'Deleted condition' in rv.data, rv.data
        rv = self.app.get('/lvfs/issue/1/condition/1/delete', follow_redirects=True)
        assert b'No condition found' in rv.data, rv.data

        # delete the issue
        rv = self.app.get('/lvfs/issue/1/delete', follow_redirects=True)
        assert b'Deleted issue' in rv.data, rv.data
        rv = self.app.get('/lvfs/issue/1/delete', follow_redirects=True)
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
        rv = self.app.get('/lvfs/issue/1/priority/down', follow_redirects=True)
        assert b'>-1<' in rv.data, rv.data
        self.logout()

        # let alice create an issue
        self.login('alice@fwupd.org')
        self.add_issue(issue_id=2, name='Secret')
        self.add_issue_condition(issue_id=2)
        self.enable_issue(issue_id=2)
        rv = self.app.get('/lvfs/issue/2/priority/up', follow_redirects=True)
        assert b'>1<' in rv.data, rv.data
        self.logout()

        # bob can only see the admin issue, not the one from alice
        self.login('bob@fwupd.org')
        rv = self.app.get('/lvfs/issue/all')
        assert b'Shared' in rv.data, rv.data
        assert b'Secret' not in rv.data, rv.data

        # we can only view the admin issue
        rv = self.app.get('/lvfs/issue/1/condition/1/delete', follow_redirects=True)
        assert b'Unable to delete condition from report' in rv.data, rv.data
        rv = self.app.get('/lvfs/issue/1/delete', follow_redirects=True)
        assert b'Unable to delete report' in rv.data, rv.data
        rv = self.app.get('/lvfs/issue/1/details')
        assert b'Shared' in rv.data, rv.data

        # we can't do anything to the secret issue
        rv = self.app.get('/lvfs/issue/2/condition/1/delete', follow_redirects=True)
        assert b'Unable to delete condition from report' in rv.data, rv.data
        rv = self.app.get('/lvfs/issue/2/delete', follow_redirects=True)
        assert b'Unable to delete report' in rv.data, rv.data
        rv = self.app.get('/lvfs/issue/2/details')
        assert b'Unable to view issue details' in rv.data, rv.data
        rv = self.app.get('/lvfs/issue/2/priority/up', follow_redirects=True)
        assert b'Unable to change issue priority' in rv.data, rv.data

    def test_download_repeat(self):

        # upload a file
        self.login()
        self.upload()

        # download a few times
        for _ in range(5):
            rv = self.app.get('/downloads/7514fc4b0e1a306337de78c58f10e9e68f791de2-hughski-colorhug2-2.0.3.cab',
                              environ_base={'HTTP_USER_AGENT': 'fwupd/1.1.1'})
            assert rv.status_code == 200, rv.status_code

    def test_download_old_fwupd(self):

        # upload a file
        self.login()
        self.upload()

        # download with a new version of fwupd
        rv = self.app.get('/downloads/7514fc4b0e1a306337de78c58f10e9e68f791de2-hughski-colorhug2-2.0.3.cab',
                          environ_base={'HTTP_USER_AGENT': 'fwupd/1.0.5'})
        assert rv.status_code == 200, rv.status_code

        # download with an old gnome-software and a new fwupd
        rv = self.app.get('/downloads/7514fc4b0e1a306337de78c58f10e9e68f791de2-hughski-colorhug2-2.0.3.cab',
                          environ_base={'HTTP_USER_AGENT': 'gnome-software/3.20.5 fwupd/1.0.5'})
        assert rv.status_code == 200, rv.status_code

        # download with an old version of fwupd
        rv = self.app.get('/downloads/7514fc4b0e1a306337de78c58f10e9e68f791de2-hughski-colorhug2-2.0.3.cab',
                          environ_base={'HTTP_USER_AGENT': 'fwupd/0.7.9999'})
        assert rv.status_code == 412, rv.status_code
        assert b'fwupd version too old' in rv.data, rv.data

if __name__ == '__main__':
    unittest.main()
