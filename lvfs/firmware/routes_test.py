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
import gzip
import io

sys.path.append(os.path.realpath('.'))

from lvfs.testcase import LvfsTestCase

def _gzip_decompress_buffer(buf):
    fgz = io.BytesIO()
    fgz.write(buf)
    fgz.seek(0)
    buf_d = None
    with gzip.GzipFile(fileobj=fgz, mode='rb') as gzip_obj:
        try:
            buf_d = gzip_obj.read()
        except IOError as e:
            print(e, buf)
    fgz.close()
    return buf_d

class LocalTestCase(LvfsTestCase):

    def test_firmware_nuke(self):

        # upload firmware
        self.login()
        rv = self._upload('contrib/hughski-colorhug2-2.0.3.cab', 'private')
        self._ensure_checksums_from_upload()
        assert self.checksum_upload_sha256 in rv.data.decode('utf-8'), rv.data
        rv = self.app.get('/lvfs/firmware/1')
        assert '>☠ Nuke ☠<' not in rv.data.decode('utf-8'), rv.data
        rv = self.app.get('/lvfs/firmware/1/nuke', follow_redirects=True)
        assert b'Cannot nuke file not yet deleted' in rv.data, rv.data
        self.delete_firmware()
        rv = self.app.get('/lvfs/firmware/1')
        assert '>☠ Nuke ☠<' in rv.data.decode('utf-8'), rv.data
        rv = self.app.get('/lvfs/firmware/1/nuke', follow_redirects=True)
        assert b'No firmware has been uploaded' in rv.data, rv.data

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

    def test_firmware_limits_report_failure(self):

        # upload firmware
        self.login()
        self.add_namespace()
        self.upload()

        # enable emails
        rv = self.app.post('/lvfs/users/1/modify_by_admin',
                           data={'qa': '1',
                                 'approved-public': '1'},
                           follow_redirects=True)
        assert b'Updated profile' in rv.data, rv.data
        rv = self.app.post('/lvfs/users/1/modify',
                           data={'notify-demote-failures': '1'},
                           follow_redirects=True)
        assert b'Updated profile' in rv.data, rv.data

        # change the failure minimum
        rv = self.app.post('/lvfs/firmware/1/modify', data=dict(
            failure_minimum='1',
        ), follow_redirects=True)
        assert b'Firmware updated' in rv.data, rv.data

        # move to stable
        self.run_cron_firmware()
        rv = self.app.get('/lvfs/firmware/1/promote/stable',
                          follow_redirects=True)
        assert b'>stable<' in rv.data, rv.data.decode()

        # upload a failed report
        rv = self._report(signed=True, updatestate=3)
        assert b'"success": true' in rv.data, rv.data

        # run cron
        self.run_cron_stats()

        # check the firmware was demoted
        rv = self.app.get('/lvfs/eventlog')
        assert b'Demoted firmware' in rv.data, rv.data
        assert b'Not sending email' in rv.data, rv.data
        rv = self.app.get('/lvfs/firmware/1')
        assert b'>testing<' in rv.data, rv.data

    def test_anonymize_db(self):

        # upload firmware
        self.login()
        self.add_namespace()
        self.upload()
        self.logout()

        # anonymize everything
        from lvfs import db, app
        from lvfs.dbutils import anonymize_db
        with app.app_context():
            anonymize_db(db)

        # check the device is not listed
        self.login()
        rv = self.app.get('/lvfs/firmware/')
        assert b'ColorHug2' not in rv.data, rv.data

    def test_firmware_limits(self):

        # upload firmware
        self.login()
        self.add_namespace()
        self.upload()

        # check no limits set
        rv = self.app.get('/lvfs/firmware/1/limits',
                          follow_redirects=True)
        assert rv.status_code == 200, rv.status_code
        assert b'ETOOSLOW' not in rv.data, rv.data

        # set download limit of 2
        rv = self.app.post('/lvfs/firmware/limit/create', data=dict(
            firmware_id='1',
            value='2',
            user_agent_glob='fwupd/*',
            response='ETOOSLOW',
        ), follow_redirects=True)
        assert b'ETOOSLOW' in rv.data, rv.data
        assert b'Added limit' in rv.data, rv.data

        # download twice, both, success
        for _ in range(2):
            self._download_firmware(useragent='fwupd/1.1.1')

        # download, fail
        rv = self.app.get('/downloads/' + self.checksum_upload_sha256 + '-hughski-colorhug2-2.0.3.cab',
                          environ_base={'HTTP_USER_AGENT': 'fwupd/1.1.1'})
        assert rv.status_code == 429, rv.status_code
        assert rv.data == b'ETOOSLOW', rv.data

        # download not matching glob, success
        self._download_firmware(useragent='wget/1.2.3')

        # delete download limit
        rv = self.app.get('/lvfs/firmware/limit/1/delete',
                          follow_redirects=True)
        assert b'Deleted limit' in rv.data, rv.data

        # check no limits set
        rv = self.app.get('/lvfs/firmware/1/limits',
                          follow_redirects=True)
        assert rv.status_code == 200, rv.status_code
        assert b'ETOOSLOW' not in rv.data, rv.data

        # download, success
        self._download_firmware(useragent='fwupd/1.1.1')

    def test_cron_firmware(self):

        # upload file, which will be unsigned
        self.login()
        self.add_namespace()
        self.upload('embargo')
        rv = self.app.get('/lvfs/firmware/1')
        assert b'Signed:' not in rv.data, rv.data
        rv = self.app.get('/lvfs/firmware/1/problems')
        assert b'Firmware is unsigned' in rv.data, rv.data

        # run the cron job manually
        self.run_cron_firmware()

        # verify the firmware is now signed
        rv = self.app.get('/lvfs/firmware/1')
        assert b'Signed:' in rv.data, rv.data
        rv = self.app.get('/lvfs/firmware/1/problems')
        assert b'Firmware is unsigned' not in rv.data, rv.data

    def test_user_only_view_own_firmware(self):

        # create User:alice, User:bob, Analyst:clara, and QA:mario
        self.login()
        self.add_user('alice@fwupd.org')
        self.add_user('bob@fwupd.org')
        self.add_user('clara@fwupd.org', is_analyst=True)
        self.add_user('mario@fwupd.org', is_qa=True, is_approved_public=True)
        self.add_namespace(vendor_id=2)
        self.logout()

        # let alice upload a file to embargo
        self.login('alice@fwupd.org')
        self.upload('embargo')
        rv = self.app.get('/lvfs/firmware/1')
        assert '/downloads/' + self.checksum_upload_sha256 in rv.data.decode('utf-8'), rv.data
        rv = self.app.get('/lvfs/firmware/')
        assert b'/lvfs/firmware/1' in rv.data, rv.data
        rv = self.app.get('/lvfs/firmware/1/analytics/clients', follow_redirects=True)
        assert b'Insufficient permissions to view analytics' in rv.data, rv.data
        self.logout()

        # bob can't see the file, nor can upload a duplicate
        self.login('bob@fwupd.org')
        rv = self._upload('contrib/hughski-colorhug2-2.0.3.cab', 'embargo')
        assert b'Another user has already uploaded this firmware' in rv.data, rv.data
        rv = self.app.get('/lvfs/firmware/1', follow_redirects=True)
        assert b'Insufficient permissions to view firmware' in rv.data, rv.data
        rv = self.app.get('/lvfs/firmware/')
        assert b'No firmware has been uploaded' in rv.data, rv.data
        rv = self.app.get('/lvfs/firmware/1/analytics/clients', follow_redirects=True)
        assert b'Insufficient permissions to view analytics' in rv.data, rv.data
        self.logout()

        # clara can see all firmwares, but can't promote them
        self.login('clara@fwupd.org')
        rv = self.app.get('/lvfs/firmware/1')
        assert '/downloads/' + self.checksum_upload_sha256 in rv.data.decode('utf-8'), rv.data
        rv = self.app.get('/lvfs/firmware/')
        assert b'/lvfs/firmware/1' in rv.data, rv.data
        rv = self.app.get('/lvfs/firmware/1/promote/testing',
                          follow_redirects=True)
        assert b'Permission denied: No QA access' in rv.data, rv.data
        self.logout()

        # mario can see things from both users and promote
        self.login('mario@fwupd.org')
        rv = self.app.get('/lvfs/firmware/1')
        assert '/downloads/' + self.checksum_upload_sha256 in rv.data.decode('utf-8'), rv.data
        rv = self.app.get('/lvfs/firmware/')
        assert b'/lvfs/firmware/1' in rv.data, rv.data
        self.run_cron_firmware()
        rv = self.app.get('/lvfs/firmware/1/promote/testing',
                          follow_redirects=True)
        assert b'>testing<' in rv.data, rv.data.decode()
        self.logout()

    def test_vendor_split_with_reparent(self):

        # add vendor1 and user, then upload firmware
        self.login()
        self.add_vendor('acme') # 2
        self.add_user('alice@acme.com', 'acme') # 3
        self.logout()
        self.login('alice@acme.com')
        self.upload()
        self.logout()

        # add vendor2 and move user to that
        self.login()
        self.add_vendor('odm') # 3
        rv = self.app.post('/lvfs/users/3/modify_by_admin', data=dict(
            vendor_id='3',
            reparent='1',
        ), follow_redirects=True)
        assert b'Updated profile' in rv.data, rv.data
        rv = self.app.get('/lvfs/users/')
        assert b'>odm<' in rv.data, rv.data
        assert b'>acme<' not in rv.data, rv.data

        # ensure firmware is reparented
        rv = self.app.get('/lvfs/firmware/1')
        assert b'The firmware is now owned by <code>odm</code>' in rv.data, rv.data
        self.logout()

        # ensure user can still view firmware
        self.login('alice@acme.com', accept_agreement=False)
        rv = self.app.get('/lvfs/firmware/')
        assert b'ColorHug2' in rv.data, rv.data

    def test_affiliated_qa_user_cannot_promote(self):

        # add two different OEM vendors, and a shared ODM
        self.login()
        self.add_vendor('oem1')  # 2
        self.add_vendor('oem2')  # 3
        self.add_vendor('odm')   # 4
        self.add_affiliation(2, 4)
        self.add_affiliation(3, 4)

        # add namespace
        self.add_namespace(vendor_id=2, value='com.hughski')

        # add alice@odm.com to vendor odm as a QA user and bob as a normal user
        self.add_user('alice@odm.com', 'odm', is_qa=True)
        self.add_user('bob@odm.com', 'odm')
        self.logout()

        # bob uploads foo.cab on behalf of vendor oem1 (vendor_id = oem1, user_id=bob)
        self.login('bob@odm.com')
        self.upload(vendor_id=2)
        self.logout()

        # check alice can't see or promote the irmware uploaded by bob
        self.login('alice@odm.com')
        rv = self.app.get('/lvfs/firmware/',
                          follow_redirects=True)
        assert b'No firmware has been uploaded' in rv.data, rv.data
        rv = self.app.get('/lvfs/firmware/1/promote/testing',
                          follow_redirects=True)
        assert b'Permission denied: No QA access to 1' in rv.data, rv.data

    def test_oem_firmware_in_odm_metadata(self):

        self.login()
        self.add_vendor('oem')  # 2
        self.add_namespace(vendor_id=2, value='com.hughski')
        self.add_user('alice@oem.com', 'oem')
        self.add_vendor('odm')  # 3
        self.add_user('bob@odm.com', 'odm')
        self.add_vendor('another-unrelated-oem')  # 4
        self.add_affiliation(2, 3)
        rv = self.app.post('/lvfs/vendors/2/modify_by_admin', data={}, follow_redirects=True)
        assert b'Updated vendor' in rv.data, rv.data
        rv = self.app.post('/lvfs/vendors/3/modify_by_admin', data={}, follow_redirects=True)
        assert b'Updated vendor' in rv.data, rv.data
        self.logout()

        # test uploading to a OEM account we have an affiliation with
        self.login('bob@odm.com')
        self.upload(vendor_id=2)
        rv = self.app.get('/lvfs/firmware/1/promote/embargo',
                          follow_redirects=True)
        assert b'Moved firmware' in rv.data, rv.data
        self.logout()

        # run the cron jobs manually
        self.run_cron_firmware()
        self.run_cron_metadata(['embargo-oem', 'embargo-odm'])

        # verify the firmware is present for the odm
        rv = self.app.get('/downloads/firmware-6f8926be2d4543878d451be96eb7221eb4313dda.xml.gz')
        xml = _gzip_decompress_buffer(rv.data)
        assert 'com.hughski.ColorHug2.firmware' in xml.decode('utf-8'), xml

        # verify the firmware is present for the oem
        rv = self.app.get('/downloads/firmware-ce7d5a03f067ff4ec73901dbacd378785dea1176.xml.gz')
        xml = _gzip_decompress_buffer(rv.data)
        assert 'com.hughski.ColorHug2.firmware' in xml.decode('utf-8'), xml

        # remove affiliation as admin
        self.login()
        rv = self.app.get('/lvfs/vendors/2/affiliation/1/delete', follow_redirects=True)
        assert b'Deleted affiliation' in rv.data, rv.data
        rv = self.app.get('/lvfs/vendors/2/affiliations')
        assert b'No affiliations exist' in rv.data, rv.data

    def test_download_repeat(self):

        # upload a file
        self.login()
        self.add_namespace()
        self.upload()

        # download a few times
        for _ in range(5):
            self._download_firmware()

    def test_download_old_fwupd(self):

        # upload a file
        self.login()
        self.add_namespace()
        self.upload()

        # download with a new version of fwupd
        self._download_firmware(useragent='fwupd/1.0.5')

        # download with an old gnome-software and a new fwupd
        self._download_firmware(useragent='gnome-software/3.20.5 fwupd/1.0.5')

        # download with an old version of fwupd
        rv = self.app.get('/downloads/' + self.checksum_upload_sha256 + '-hughski-colorhug2-2.0.3.cab',
                          environ_base={'HTTP_USER_AGENT': 'fwupd/0.7.9999'})
        assert rv.status_code == 412, rv.status_code
        #assert b'fwupd version too old' in rv.data, rv.data

    def test_agreement_upload_not_signed(self):

        # add a user and try to upload firmware without signing the agreement
        self.login()
        self.add_user('testuser@fwupd.org')
        self.logout()
        self.login('testuser@fwupd.org', accept_agreement=False)
        rv = self._upload('contrib/hughski-colorhug2-2.0.3.cab', 'private')
        assert b'User has not signed legal agreement' in rv.data, rv.data

    def test_plugin_blocklist(self):

        self.login()
        self.upload(filename='contrib/blocklist.cab', target='private')
        rv = self.app.get('/lvfs/firmware/1/tests')
        assert 'CRC: 0x85f035a8' in rv.data.decode('utf-8'), rv.data.decode()
        assert 'DFU Length: 0x10' in rv.data.decode('utf-8'), rv.data
        assert 'DFU Version: 0x0100' in rv.data.decode('utf-8'), rv.data
        assert 'IbvExampleCertificate' in rv.data.decode('utf-8'), rv.data.decode()
        assert 'DO NOT SHIP' in rv.data.decode('utf-8'), rv.data.decode()

    def test_plugin_intelme(self):

        self.login()
        self.upload(filename='contrib/intelme.cab', target='private')
        rv = self.app.get('/lvfs/firmware/1/tests')

        # UEFI Capsule
        assert 'CapsuleImageSize: 0x78' in rv.data.decode('utf-8'), rv.data
        assert 'GUID: cc4cbfa9-bf9d-540b-b92b-172ce31013c1' in rv.data.decode('utf-8'), rv.data
        assert 'IbvExampleCertificate' in rv.data.decode('utf-8')
        assert 'DO NOT SHIP' in rv.data.decode('utf-8'), rv.data.decode()
        assert 'Found $MN2' in rv.data.decode('utf-8'), rv.data.decode()

if __name__ == '__main__':
    unittest.main()
