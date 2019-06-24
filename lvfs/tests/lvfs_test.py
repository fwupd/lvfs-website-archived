#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2018 Richard Hughes <richard@hughsie.com>
#
# SPDX-License-Identifier: GPL-2.0+
#
# pylint: disable=fixme,too-many-public-methods,line-too-long,too-many-lines
# pylint: disable=too-many-instance-attributes,wrong-import-position

import os
import sys
import datetime
import unittest
import tempfile
import subprocess
import gzip
import io

from contextlib import redirect_stdout

# allows us to run this from the project root
sys.path.append(os.path.realpath('.'))

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

class LvfsTestCase(unittest.TestCase):

    def setUp(self):

        # global checksums
        self.checksum_upload = None
        self.checksum_signed = None

        # create new database
        self.db_fd, self.db_filename = tempfile.mkstemp()
        self.db_uri = 'sqlite:///' + self.db_filename

        # write out custom settings file
        self.cfg_fd, self.cfg_filename = tempfile.mkstemp()
        with open(self.cfg_filename, 'w') as cfgfile:
            cfgfile.write('\n'.join([
                "SQLALCHEMY_DATABASE_URI = '%s'" % self.db_uri,
                "SQLALCHEMY_TRACK_MODIFICATIONS = False",
                "DEBUG = True",
                "CERTTOOL = 'flatpak run --command=certtool --filesystem=/tmp:ro org.freedesktop.fwupd'",
                "RESTORE_DIR = '/tmp'",
                "DOWNLOAD_DIR = '/tmp'",
                "SECRET_PASSWORD_SALT = 'lvfs%%%'",
                "SECRET_ADDR_SALT = 'addr%%%'",
                "SECRET_VENDOR_SALT = 'vendor%%%'",
                "MAIL_SUPPRESS_SEND = True",
                ]))

        # create instance
        import lvfs
        from lvfs import db
        from lvfs.dbutils import init_db
        self.app = lvfs.app.test_client()
        lvfs.app.config.from_pyfile(self.cfg_filename)
        with lvfs.app.app_context():
            init_db(db)

        # ensure the plugins settings are set up
        self.login()
        self.app.get('/lvfs/settings_create')
        self.app.get('/lvfs/agreement/create')
        self.app.get('/lvfs/agreement/1/accept')
        for value in ['com.hughski.colorhug', 'org.usb.dfu', 'org.uefi.capsule']:
            rv = self.app.post('/lvfs/protocol/add', data=dict(
                value=value,
            ), follow_redirects=True)
            assert b'Added protocol' in rv.data, rv.data
        for value in ['X-Device', 'X-ManagementEngine']:
            rv = self.app.post('/lvfs/category/add', data=dict(
                value=value,
            ), follow_redirects=True)
            assert b'Added category' in rv.data, rv.data
        rv = self.app.post('/lvfs/settings/modify', data=dict(
            clamav_enable='disabled',
            chipsec_size_min='0',
        ), follow_redirects=True)
        assert b'Updated settings' in rv.data, rv.data
        self.logout()

    def tearDown(self):
        os.close(self.db_fd)
        os.unlink(self.db_filename)
        os.close(self.cfg_fd)
        os.unlink(self.cfg_filename)

    def _login(self, username, password='Pa$$w0rd'):
        return self.app.post('/lvfs/login', data=dict(
            username=username,
            password=password
        ), follow_redirects=True)

    def _logout(self):
        return self.app.get('/lvfs/logout', follow_redirects=True)

    def login(self, username='sign-test@fwupd.org', password='Pa$$w0rd', accept_agreement=True):
        rv = self._login(username, password)
        assert b'/lvfs/upload' in rv.data, rv.data
        assert b'Incorrect username' not in rv.data, rv.data
        if accept_agreement and username != 'sign-test@fwupd.org':
            rv = self.app.get('/lvfs/agreement/1/accept', follow_redirects=True)
            assert b'Recorded acceptance of the agreement' in rv.data, rv.data

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
            display_name='Generic Name',
        ), follow_redirects=True)

    def add_user(self, username='testuser@fwupd.org', group_id='testgroup',
                 password='Pa$$w0rd', is_qa=False, is_analyst=False,
                 is_vendor_manager=False, is_approved_public=False, is_robot=False):
        rv = self._add_user(username, group_id, password)
        assert b'Added user' in rv.data, rv.data
        user_id_idx = rv.data.decode('utf-8').find('Added user ')
        assert user_id_idx != -1, rv.data
        user_id = int(rv.data[user_id_idx+11:user_id_idx+12])
        assert user_id != 0, rv.data
        if is_qa or is_analyst or is_vendor_manager or is_approved_public or is_robot:
            data = {'auth_type': 'local'}
            if is_qa:
                data['is_qa'] = '1'
            if is_analyst:
                data['is_analyst'] = '1'
            if is_vendor_manager:
                data['is_vendor_manager'] = '1'
            if is_approved_public:
                data['is_approved_public'] = '1'
            if is_robot:
                data['is_robot'] = '1'
            rv = self.app.post('/lvfs/user/%i/modify_by_admin' % user_id,
                               data=data, follow_redirects=True)
            assert b'Updated profile' in rv.data, rv.data

    def _upload(self, filename='contrib/hughski-colorhug2-2.0.3.cab', target='private', vendor_id=None):
        with open(filename, 'rb') as fd:
            data = {
                'target': target,
                'file': (fd, filename)
            }
            if vendor_id:
                data['vendor_id'] = vendor_id
            return self.app.post('/lvfs/upload', data=data, follow_redirects=True)

    def _ensure_checksums_from_upload(self):
        # peek into the database to get the checksums
        from lvfs import db
        from lvfs.models import Firmware
        fw = db.session.query(Firmware).first()
        self.checksum_upload = fw.checksum_upload
        self.checksum_signed = fw.checksum_signed

    def upload(self, target='private', vendor_id=None, filename='contrib/hughski-colorhug2-2.0.3.cab', fwchecks=True):
        rv = self._upload(filename, target, vendor_id)
        assert b'Uploaded file' in rv.data, rv.data
        self._ensure_checksums_from_upload()
        assert self.checksum_upload.encode('utf-8') in rv.data, rv.data
        if fwchecks:
            self.run_cron_fwchecks()

    def test_login_logout(self):

        # test logging in and out
        rv = self._login('sign-test@fwupd.org', 'Pa$$w0rd')
        assert b'/lvfs/upload' in rv.data, rv.data
        rv = self._logout()
        rv = self._login('sign-test@fwupd.org', 'Pa$$w0rd')
        assert b'/lvfs/upload' in rv.data, rv.data
        rv = self._logout()
        assert b'/lvfs/upload' not in rv.data, rv.data
        rv = self._login('sign-test@fwupd.orgx', 'default')
        assert b'Incorrect username' in rv.data, rv.data
        rv = self._login('sign-test@fwupd.org', 'defaultx')
        assert b'Incorrect password' in rv.data, rv.data

    def test_plugin_blocklist(self):

        self.login()
        self.upload(filename='contrib/blocklist.cab', target='private')
        rv = self.app.get('/lvfs/firmware/1/tests')
        assert 'CRC: 0x85f035a8' in rv.data.decode('utf-8'), rv.data
        assert 'DFU Length: 0x10' in rv.data.decode('utf-8'), rv.data
        assert 'DFU Version: 0x0100' in rv.data.decode('utf-8'), rv.data
        assert 'Found: DO NOT SHIP' in rv.data.decode('utf-8'), rv.data

    def test_plugin_chipsec(self):

        self.login()
        self.upload(filename='contrib/chipsec.cab', target='private')
        rv = self.app.get('/lvfs/firmware/1/tests')

        # UEFI Capsule
        assert 'HeaderSize: 0x1c' in rv.data.decode('utf-8'), rv.data
        assert 'GUID: cc4cbfa9-bf9d-540b-b92b-172ce31013c1' in rv.data.decode('utf-8'), rv.data

        # does not always exist
        if not os.path.exists('/usr/bin/chipsec_util'):
            return

        # CHIPSEC -> Blocklist
        assert 'Found PFS in Zlib compressed blob' in rv.data.decode('utf-8'), rv.data
        assert 'Found: DO NOT TRUST' in rv.data.decode('utf-8'), rv.data

        # edit a shard description
        rv = self.app.get('/lvfs/shard/all')
        assert 'com.intel.Uefi.Driver.00_S_PE32' in rv.data.decode('utf-8'), rv.data
        assert '12345678-1234-5678-1234-567812345678' in rv.data.decode('utf-8'), rv.data
        rv = self.app.get('/lvfs/shard/1/details')
        assert 'com.intel.Uefi.Driver.00_S_PE32' in rv.data.decode('utf-8'), rv.data
        rv = self.app.post('/lvfs/shard/1/modify', data=dict(
            description='Hello Dave',
        ), follow_redirects=True)
        assert b'Modified shard' in rv.data, rv.data
        assert b'Hello Dave' in rv.data, rv.data

        # view component certificates
        rv = self.app.get('/lvfs/component/1/certificates')
        assert 'Default Company Ltd' in rv.data.decode('utf-8'), rv.data

    def test_plugin_intelme(self):

        self.login()
        self.upload(filename='contrib/intelme.cab', target='private')
        rv = self.app.get('/lvfs/firmware/1/tests')

        # UEFI Capsule
        assert 'CapsuleImageSize: 0x78' in rv.data.decode('utf-8'), rv.data
        assert 'GUID: cc4cbfa9-bf9d-540b-b92b-172ce31013c1' in rv.data.decode('utf-8'), rv.data
        assert 'Found: DO NOT SHIP' in rv.data.decode('utf-8'), rv.data
        assert 'Found $MN2' in rv.data.decode('utf-8'), rv.data

    def test_upload_invalid(self):

        # upload something that isn't a cabinet archive
        self.login()
        rv = self._upload('contrib/Dockerfile', 'private')
        assert b'Failed to upload file' in rv.data, rv.data
        rv = self._upload('contrib/hughski-colorhug2-2.0.3.cab', 'NOTVALID')
        assert b'Target not valid' in rv.data, rv.data

    def test_firmware_nuke(self):

        # upload firmware
        self.login()
        rv = self._upload('contrib/hughski-colorhug2-2.0.3.cab', 'private')
        self._ensure_checksums_from_upload()
        assert self.checksum_upload in rv.data.decode('utf-8'), rv.data
        rv = self.app.get('/lvfs/firmware/1')
        assert '>☠ Nuke ☠<' not in rv.data.decode('utf-8'), rv.data
        rv = self.app.get('/lvfs/firmware/1/nuke', follow_redirects=True)
        assert b'Cannot nuke file not yet deleted' in rv.data, rv.data
        self.delete_firmware()
        rv = self.app.get('/lvfs/firmware/1')
        assert '>☠ Nuke ☠<' in rv.data.decode('utf-8'), rv.data
        rv = self.app.get('/lvfs/firmware/1/nuke', follow_redirects=True)
        assert b'No firmware has been uploaded' in rv.data, rv.data

    def _download_firmware(self, useragent='fwupd/1.1.1'):
        rv = self.app.get('/downloads/' + self.checksum_upload + '-hughski-colorhug2-2.0.3.cab',
                          environ_base={'HTTP_USER_AGENT': useragent})
        assert rv.status_code == 200, rv.status_code
        assert len(rv.data) > 10000, len(rv.data)
        assert len(rv.data) < 20000, len(rv.data)

    def test_upload_valid(self):

        # upload firmware
        self.login()
        rv = self._upload('contrib/hughski-colorhug2-2.0.3.cab', 'private')
        self._ensure_checksums_from_upload()
        assert self.checksum_upload in rv.data.decode('utf-8'), rv.data
        rv = self.app.get('/lvfs/firmware/1/components')
        assert b'com.hughski.ColorHug2.firmware' in rv.data, rv.data

        # download
        self._download_firmware()

        # check analytics works
        uris = ['/lvfs/firmware/1/analytics',
                '/lvfs/firmware/1/analytics/clients',
                '/lvfs/firmware/1/analytics/reports']
        for uri in uris:
            rv = self.app.get(uri)
            assert b'favicon.ico' in rv.data, rv.data
            assert b'LVFS: Error' not in rv.data, rv.data

        # check component view shows GUID
        rv = self.app.get('/lvfs/component/1')
        assert b'2082b5e0-7a64-478a-b1b2-e3404fab6dad' in rv.data, rv.data

        # check private firmware isn't visible when not logged in
        rv = self.app.get('/lvfs/device')
        assert b'2082b5e0-7a64-478a-b1b2-e3404fab6dad' not in rv.data, rv.data
        rv = self.app.get('/lvfs/device/com.hughski.ColorHug2.firmware')
        # FIXME is it a bug that we show the device exists even though it's not got any mds?
        assert b'MCDC04 errata' not in rv.data, rv.data
        rv = self.app.get('/lvfs/devicelist')
        assert b'ColorHug' not in rv.data, rv.data
        self.login()

        # promote the firmware to testing then stable
        self.run_cron_firmware()
        self.run_cron_fwchecks()
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
        rv = self.app.get('/lvfs/device/com.hughski.ColorHug2.firmware')
        assert b'MCDC04 errata' in rv.data, rv.data
        self.login()

        # download it
        self._download_firmware()

        # test deleting the firmware
        self.delete_firmware()

        # download deleted file
        self._download_firmware()

        # re-upload the same file
        rv = self._upload('contrib/hughski-colorhug2-2.0.3.cab', 'private')
        assert b'Failed to upload file: A file with hash' in rv.data, rv.data

        # undelete it
        rv = self.app.get('/lvfs/firmware/1/undelete', follow_redirects=True)
        assert b'Firmware undeleted' in rv.data, rv.data

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

    def test_anonymize_db(self):

        # upload firmware
        self.login()
        self.upload()
        self.logout()

        # anonymize everything
        from lvfs import db, app
        from lvfs.dbutils import anonymize_db
        with app.app_context():
            anonymize_db(db)

        # check the device is not listed
        self.login()
        rv = self.app.get('/lvfs/firmware')
        assert b'ColorHug2' not in rv.data, rv.data

    def test_firmware_limits(self):

        # upload firmware
        self.login()
        self.upload()

        # check no limits set
        rv = self.app.get('/lvfs/firmware/1/limits',
                          follow_redirects=True)
        assert rv.status_code == 200, rv.status_code
        assert b'ETOOSLOW' not in rv.data, rv.data

        # set download limit of 2
        rv = self.app.post('/lvfs/firmware/limit/add', data=dict(
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
        rv = self.app.get('/downloads/' + self.checksum_upload + '-hughski-colorhug2-2.0.3.cab',
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

    @staticmethod
    def run_cron_firmware(fn='hughski-colorhug2-2.0.3'):

        from lvfs import app
        from cron import _regenerate_and_sign_firmware
        with app.test_request_context():
            with io.StringIO() as buf, redirect_stdout(buf):
                _regenerate_and_sign_firmware()
                stdout = buf.getvalue()

        assert fn in stdout, stdout

    @staticmethod
    def run_cron_stats():

        from lvfs import app
        from cron import _generate_stats_for_datestr, _generate_stats
        from lvfs.models import _get_datestr_from_datetime
        with app.test_request_context():
            with io.StringIO() as buf, redirect_stdout(buf):
                _generate_stats_for_datestr(_get_datestr_from_datetime(datetime.date.today()))
                _generate_stats()
                stdout = buf.getvalue()

        assert 'generated' in stdout, stdout

    @staticmethod
    def run_cron_metadata(remote_ids=None):

        from lvfs import app
        from cron import _regenerate_and_sign_metadata
        with app.test_request_context():
            with io.StringIO() as buf, redirect_stdout(buf):
                _regenerate_and_sign_metadata()
                stdout = buf.getvalue()

        if remote_ids:
            for remote_id in remote_ids:
                assert 'Updating: %s' % remote_id in stdout, stdout

    @staticmethod
    def run_cron_fwchecks():

        from lvfs import app
        from cron import _check_firmware
        with app.test_request_context():
            with io.StringIO() as buf, redirect_stdout(buf):
                _check_firmware()

    def test_cron_metadata(self):

        # verify all metadata is in good shape
        self.login()
        rv = self.app.get('/lvfs/metadata')
        assert b'Remote will be signed with' not in rv.data, rv.data

        # upload file, dirtying the admin-embargo remote
        self.upload('embargo')
        rv = self.app.get('/lvfs/metadata')
        assert b'Remote will be signed with' in rv.data, rv.data

        # run the cron job manually
        self.run_cron_metadata(['embargo-admin'])

        # verify all metadata is in good shape
        rv = self.app.get('/lvfs/metadata')
        assert b'Remote will be signed with' not in rv.data, rv.data

    def test_cron_firmware(self):

        # upload file, which will be unsigned
        self.login()
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
        self.logout()

        # let alice upload a file to embargo
        self.login('alice@fwupd.org')
        self.upload('embargo')
        rv = self.app.get('/lvfs/firmware/1')
        assert '/downloads/' + self.checksum_upload in rv.data.decode('utf-8'), rv.data
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
        assert '/downloads/' + self.checksum_upload in rv.data.decode('utf-8'), rv.data
        rv = self.app.get('/lvfs/firmware')
        assert b'/lvfs/firmware/1' in rv.data, rv.data
        rv = self.app.get('/lvfs/firmware/1/promote/testing',
                          follow_redirects=True)
        assert b'Permission denied: No QA access' in rv.data, rv.data
        self.logout()

        # mario can see things from both users and promote
        self.login('mario@fwupd.org')
        rv = self.app.get('/lvfs/firmware/1')
        assert '/downloads/' + self.checksum_upload in rv.data.decode('utf-8'), rv.data
        rv = self.app.get('/lvfs/firmware')
        assert b'/lvfs/firmware/1' in rv.data, rv.data
        self.run_cron_firmware()
        rv = self.app.get('/lvfs/firmware/1/promote/testing',
                          follow_redirects=True)
        assert b'>testing<' in rv.data, rv.data
        self.logout()

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
        rv = self.app.get('/lvfs/eventlog')
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

    def add_vendor(self, group_id):
        rv = self.app.post('/lvfs/vendor/add', data=dict(group_id=group_id),
                           follow_redirects=True)
        assert b'Added vendor' in rv.data, rv.data

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
        rv = self.app.post('/lvfs/user/3/modify_by_admin', data=dict(
            vendor_id='3',
            reparent='1',
        ), follow_redirects=True)
        assert b'Updated profile' in rv.data, rv.data
        rv = self.app.get('/lvfs/userlist')
        assert b'>odm<' in rv.data, rv.data
        assert b'>acme<' not in rv.data, rv.data

        # ensure firmware is reparented
        rv = self.app.get('/lvfs/firmware/1')
        assert b'The firmware is now owned by <code>odm</code>' in rv.data, rv.data
        self.logout()

        # ensure user can still view firmware
        self.login('alice@acme.com', accept_agreement=False)
        rv = self.app.get('/lvfs/firmware')
        assert b'ColorHug2' in rv.data, rv.data

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
        rv = self.app.get('/lvfs/userlist')
        assert b'testuser' in rv.data, rv.data
        rv = self.app.get('/lvfs/user/3/admin')
        assert b'testuser@fwupd.org' in rv.data, rv.data
        rv = self.app.get('/lvfs/vendorlist')
        assert b'testgroup' in rv.data, rv.data

        # modify an existing user as the admin
        rv = self.app.post('/lvfs/user/3/modify_by_admin', data=dict(
            auth_type='local',
            auth_warning='Caveat Emptor',
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
        rv = self._login('testuser@fwupd.org')
        assert b'/lvfs/upload' in rv.data, rv.data
        assert b'Caveat Emptor' in rv.data, rv.data

        # ensure the user can change their own display name
        rv = self.app.post('/lvfs/user/3/modify', data=dict(
            display_name='Something Funky',
        ), follow_redirects=True)
        assert b'Updated profile' in rv.data, rv.data
        rv = self.app.get('/lvfs/profile')
        assert b'Something Funky' in rv.data, rv.data

        # ensure the user can change their own password
        rv = self.app.post('/lvfs/user/3/password', data=dict(
            password_old='not-even-close',
            password_new='Hi$$t0ry',
        ), follow_redirects=True)
        assert b'Incorrect existing password' in rv.data, rv.data
        rv = self.app.post('/lvfs/user/3/password', data=dict(
            password_old='Pa$$w0rd',
            password_new='Hi$$t0ry',
        ), follow_redirects=True)
        assert b'Updated profile' in rv.data, rv.data
        rv = self.app.get('/lvfs/profile')
        assert b'Something Funky' in rv.data, rv.data

        # try to self-delete
        rv = self.app.get('/lvfs/user/3/delete')
        assert b'Only the admin team can access this resource' in rv.data, rv.data

        # delete the user as the admin
        self.logout()
        self.login()
        rv = self.app.get('/lvfs/user/3/delete', follow_redirects=True)
        assert b'Deleted user' in rv.data, rv.data
        rv = self.app.get('/lvfs/userlist')
        assert b'testuser@fwupd.org' not in rv.data, rv.data

    def test_manager_users(self):

        # create a new vendor
        self.login()
        rv = self.app.post('/lvfs/vendor/add', data=dict(group_id='testvendor'),
                           follow_redirects=True)
        assert b'Added vendor' in rv.data, rv.data

        # set the username glob
        rv = self.app.post('/lvfs/vendor/2/modify_by_admin', data=dict(
            username_glob='*@testvendor.com,*@anothervendor.com',
        ), follow_redirects=True)
        assert b'Updated vendor' in rv.data, rv.data

        # create a manager user
        self.add_user('alice@testvendor.com', group_id='testvendor', is_vendor_manager=True)

        # log in as the manager
        self.logout()
        self.login('alice@testvendor.com')

        # try to add new user to new vendor with non-matching domain (fail)
        rv = self.app.post('/lvfs/vendor/2/user/add', data=dict(
            username='bob@hotmail.com',
            display_name='Generic Name',
        ), follow_redirects=True)
        assert b'Email address does not match account policy' in rv.data, rv.data

        # add new user with matching domain
        rv = self.app.post('/lvfs/vendor/2/user/add', data=dict(
            username='clara@testvendor.com',
            display_name='Generic Name',
        ), follow_redirects=True)
        assert b'Added user' in rv.data, rv.data

        # change the new user to allow a local login
        rv = self.app.post('/lvfs/user/4/modify_by_admin', data=dict(
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
        assert b'Permission denied' in rv.data, rv.data
        rv = self.app.get('/lvfs/firmware/1/promote/stable',
                          follow_redirects=True)
        assert b'Permission denied' in rv.data, rv.data

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
        self.run_cron_firmware()
        rv = self.app.get('/lvfs/firmware/1/promote/testing',
                          follow_redirects=True)
        assert b'Moved firmware' in rv.data, rv.data
        assert b'>testing<' in rv.data, rv.data
        rv = self.app.get('/lvfs/firmware/1/promote/stable',
                          follow_redirects=True)
        assert b'Moved firmware' in rv.data, rv.data
        assert b'>stable<' in rv.data, rv.data

        # build the pulp metadata
        self.logout()
        self.run_cron_metadata(['stable'])
        self.login()

        # demote back to testing then private
        rv = self.app.get('/lvfs/firmware/1/promote/testing',
                          follow_redirects=True)
        assert b'Moved firmware' in rv.data, rv.data
        assert b'>testing<' in rv.data, rv.data
        rv = self.app.get('/lvfs/firmware/1/promote/private',
                          follow_redirects=True)
        assert b'Moved firmware' in rv.data, rv.data
        assert b'>private<' in rv.data, rv.data

    def _report(self, updatestate=2, distro_id='fedora', checksum=None, signed=False, signature_valid=True):
        if not checksum:
            checksum = self.checksum_signed
        payload = """
{
  "ReportVersion" : 2,
  "MachineId" : "abc",
  "Metadata" : {
    "DistroId" : "%s",
    "DistroVersion" : "27",
    "DistroVariant" : "workstation"
  },
  "Reports" : [
    {
      "Checksum" : "%s",
      "UpdateState" : %i,
      "UpdateError" : "UEFI firmware update failed: failed to make /boot/efi/EFI/arch/fw: No such file or directory",
      "Guid" : "7514fc4b0e1a306337de78c58f10e9e68f791de2",
      "Plugin" : "colorhug",
      "VersionOld" : "2.0.0",
      "VersionNew" : "2.0.3",
      "Flags" : 34,
      "Created" : 1518212684,
      "Modified" : 1518212754,
      "Metadata" : {
        "AppstreamGlibVersion" : "0.7.5",
        "CpuArchitecture" : "x86_64",
        "FwupdVersion" : "1.0.5",
        "GUsbVersion" : "0.2.11",
        "BootTime" : "1518082325",
        "KernelVersion" : "4.14.16-300.fc27.x86_64"
      }
    }
  ]
} """ % (distro_id, checksum, updatestate)

        # legacy
        if not signed:
            return self.app.post('/lvfs/firmware/report', data=payload)

        # signed
        if signature_valid:
            if 'LVFS_RECREATE_CERT' in os.environ:
                dat = tempfile.NamedTemporaryFile(mode='wb',
                                                  prefix='pkcs7_',
                                                  suffix=".cab",
                                                  dir=None,
                                                  delete=True)
                dat.write(payload.encode('utf8'))
                dat.flush()
                argv = ['sudo', 'certtool', '--p7-detached-sign',
                        '--p7-time', '--no-p7-include-cert',
                        '--load-certificate', 'contrib/client.pem',
                        '--load-privkey', 'contrib/secret.key',
                        '--infile', dat.name,
                        '--outfile', 'contrib/test.p7b']
                ps = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                _, err = ps.communicate()
                if ps.returncode != 0:
                    raise IOError(err)
            with open('contrib/test.p7b', 'rb') as f:
                signature = f.read().decode('utf8')
        else:
            # signing some crazy thing
            signature = """
-----BEGIN PKCS7-----
MIICYgYJKoZIhvcNAQcCoIICUzCCAk8CAQExDTALBglghkgBZQMEAgEwCwYJKoZI
hvcNAQcBMYICLDCCAigCAQEwGDAAAhRfEaI3uZSTG774ab0BUyNYdPqPizALBglg
hkgBZQMEAgGgaTAYBgkqhkiG9w0BCQMxCwYJKoZIhvcNAQcBMBwGCSqGSIb3DQEJ
BTEPFw0xOTAzMTAxNzU1MjBaMC8GCSqGSIb3DQEJBDEiBCA5srgWrdr1OV1vxW0m
Q7zNvoxFlVkp1mrAIrVQCpUekzANBgkqhkiG9w0BAQEFAASCAYADec2WR6u++SnR
zNwZ44reU3TaVe2zCELE07aPN9pAk9V3ez8ZSGRSKo2hPWl5wzqBP8rGv4D/vTgr
r+42OHYoiAQ4113D1adMHvAmyPt20yzrWAP138C2ajeX1m7vDT0guLlEBoJPigB7
6nVYa1LCM9+EpJI+JrAEIXXTeuXIIeEROu0vvGrg1uvQeLg5ZdvqJUfbs0/fD29R
LEgNMCeQo0yqGx+511hQDybQnx1pNtSUTTsQ6o5h6W8ELLD924C0Yqd3bRf5JOdm
qWhfysGJNGlQubM4nyjks+9b5DPiZWxNdsUE+l9xQZc4gR+wJg3dfocbZ6kfo/pI
Dbskni3KiRc13+HmUBdbjhdLWYS4hirSVuyZ2n8UjIS4Pp/S2cPDe47YJwCbOn97
WmOPP+2xuvr/sTV8AAbcAZgK2TBBVUjZMJeCBcLIba8O9mJJVHE4I1PzXcf+l6D7
ma+I7fM5pmgsEL4tkCZAg0+CPTyhHkMV/cWuOZUjqTsYbDq1pZI=
-----END PKCS7-----
"""
        data = {
            'payload': payload,
            'signature': signature,
        }
        return self.app.post('/lvfs/firmware/report', data=data,
                             content_type='multipart/form-data')

    def test_reports_signed(self):

        # upload a firmware that can receive a report
        self.login()
        self.upload(target='testing')

        # send empty
        rv = self.app.post('/lvfs/firmware/report')
        assert b'No data' in rv.data, rv.data

        # a signed report that does not exist for user -- invalid is ignored
        rv = self._report(signed=True, signature_valid=False)
        assert b'"success": true' in rv.data, rv.data

        # set certificate for user
        self._add_certificate()

        # send a valid signed report
        rv = self._report(signed=True)
        assert b'"success": true' in rv.data, rv.data

        # send an invalid signed report
        rv = self._report(signed=True, signature_valid=False)
        assert b'Signature did not validate' in rv.data, rv.data

    def test_reports(self):

        # upload a firmware that can receive a report
        self.login()
        self.upload(target='testing')

        # send empty
        rv = self.app.post('/lvfs/firmware/report')
        assert b'No data' in rv.data, rv.data

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

        # download the firmware at least once
        self._download_firmware()

        # check the report appeared on download telemetry page
        self.run_cron_stats()
        rv = self.app.get('/lvfs/telemetry/0/download_cnt/down')
        assert b'ColorHug2' in rv.data, rv.data
        assert b'>1<' in rv.data, rv.data

        # check the report appeared on the success telemetry page
        self.run_cron_stats()
        rv = self.app.get('/lvfs/telemetry/0/success/down')
        assert b'ColorHug2' in rv.data, rv.data

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
        assert b'ClamAV' in rv.data, rv.data

        # dig into the Windows Update page
        rv = self.app.get('/lvfs/settings/wu-copy')
        assert b'Copy files generated' in rv.data, rv.data
        assert b'value="enabled" checked/>' in rv.data, rv.data

        # change both values to False
        rv = self.app.post('/lvfs/settings/modify/wu-copy', data=dict(
            wu_copy_inf='disabled',
            wu_copy_cat='disabled',
        ), follow_redirects=True)
        assert b'Copy files generated' in rv.data, rv.data
        assert b'value="enabled" />' in rv.data, rv.data

        # and back to True
        rv = self.app.post('/lvfs/settings/modify/wu-copy', data=dict(
            wu_copy_inf='enabled',
            wu_copy_cat='enabled',
        ), follow_redirects=True)
        assert b'value="enabled" checked/>' in rv.data, rv.data

    def test_updateinfo(self):

        # get the default update info from the firmware archive
        self.login()
        self.upload()
        rv = self.app.get('/lvfs/component/1/update')
        assert b'Work around the MCDC04 errata' in rv.data, rv.data
        assert b'value="low" selected' in rv.data, rv.data

        # edit the description and severity
        rv = self.app.post('/lvfs/component/1/modify', data=dict(
            urgency='critical',
            description='Not enough cats!',
        ), follow_redirects=True)
        assert b'Component updated' in rv.data, rv.data

        # verify the new update info
        rv = self.app.get('/lvfs/component/1/update')
        assert b'Not enough cats' in rv.data, rv.data
        assert b'value="critical" selected' in rv.data, rv.data

    def test_requires(self):

        # check existing requires were added
        self.login()
        self.upload()

        # check requirements were copied out from the .metainfo.xml file
        rv = self.app.get('/lvfs/component/1/requires')
        assert b'85d38fda-fc0e-5c6f-808f-076984ae7978' in rv.data, rv.data
        assert b'name="version" value="1.0.3' in rv.data, rv.data
        assert b'ge" selected' in rv.data, rv.data
        assert b'regex" selected' in rv.data, rv.data
        assert b'BOT03.0[2-9]_*' in rv.data, rv.data

        # remove the CHID requirement
        rv = self.app.get('/lvfs/component/1/requirement/delete/3', follow_redirects=True)
        assert b'Removed requirement 85d38fda-fc0e-5c6f-808f-076984ae7978' in rv.data, rv.data

        # add an invalid CHID
        rv = self.app.post('/lvfs/component/1/requirement/modify', data=dict(
            kind='hardware',
            value='NOVALIDGUID',
        ), follow_redirects=True)
        assert b'NOVALIDGUID is not a valid GUID' in rv.data, rv.data

        # add a valid CHID
        rv = self.app.post('/lvfs/component/1/requirement/modify', data=dict(
            kind='hardware',
            value='85d38fda-fc0e-5c6f-808f-076984ae7978',
        ), follow_redirects=True)
        assert b'85d38fda-fc0e-5c6f-808f-076984ae7978' in rv.data, rv.data
        assert b'Added requirement' in rv.data, rv.data

        # modify an existing requirement by adding it again
        rv = self.app.post('/lvfs/component/1/requirement/modify', data=dict(
            kind='id',
            value='org.freedesktop.fwupd',
            compare='ge',
            version='1.0.4',
        ), follow_redirects=True)
        assert b'name="version" value="1.0.4' in rv.data, rv.data
        assert b'Modified requirement' in rv.data, rv.data

        # delete a requirement by adding an 'any' comparison
        rv = self.app.post('/lvfs/component/1/requirement/modify', data=dict(
            kind='id',
            value='org.freedesktop.fwupd',
            compare='any',
            version='1.0.4',
        ), follow_redirects=True)
        assert b'name="version" value="1.0.4' not in rv.data, rv.data
        assert b'Deleted requirement' in rv.data, rv.data

    def test_affiliation_change_as_admin(self):

        # add oem and odm
        self.login()
        self.add_vendor('oem')  # 2
        self.add_user('alice@oem.com', 'oem')
        rv = self.app.post('/lvfs/vendor/2/modify_by_admin', data={}, follow_redirects=True)
        assert b'Updated vendor' in rv.data, rv.data
        self.add_vendor('odm')  # 3
        self.add_user('bob@odm.com', 'odm')
        rv = self.app.post('/lvfs/vendor/3/modify_by_admin', data={}, follow_redirects=True)
        assert b'Updated vendor' in rv.data, rv.data
        self.logout()

        # bob uploads to the ODM vendor
        self.login('bob@odm.com')
        self.upload(target='embargo')
        self.logout()

        # change the ownership to 'oem' as admin (no affiliation required)
        self.login()
        rv = self.app.get('/lvfs/firmware/1/affiliation')
        assert b'option value="3" selected' in rv.data, rv.data
        rv = self.app.post('/lvfs/firmware/1/affiliation/change', data=dict(
            vendor_id='2',
        ), follow_redirects=True)
        assert b'Changed firmware vendor' in rv.data, rv.data
        rv = self.app.get('/lvfs/firmware/1/affiliation')
        assert b'option value="2" selected' in rv.data, rv.data
        rv = self.app.get('/lvfs/firmware/1')
        assert b'>embargo-oem<' in rv.data, rv.data
        assert b'>embargo-odm<' not in rv.data, rv.data

    def test_affiliation_change_as_qa(self):

        # add oem and odm
        self.login()
        self.add_vendor('odm')  # 2
        self.add_vendor('oem')  # 3
        self.add_affiliation(3, 2)

        # add odm uploader and QA user
        self.add_user('alice@odm.com', 'odm')
        self.add_user('bob@odm.com', 'odm', is_qa=True)
        self.logout()

        # upload as alice
        self.login('alice@odm.com')
        self.upload(target='embargo')
        self.logout()

        # move to oem as bob
        self.login('bob@odm.com')
        rv = self.app.post('/lvfs/firmware/1/affiliation/change', data=dict(
            vendor_id='3',
        ), follow_redirects=True)
        assert b'Changed firmware vendor' in rv.data, rv.data

    def test_affiliation_change_as_user(self):

        # add oem and odm
        self.login()
        self.add_vendor('oem')  # 2
        self.add_user('alice@oem.com', 'oem')
        rv = self.app.post('/lvfs/vendor/2/modify_by_admin', data={}, follow_redirects=True)
        assert b'Updated vendor' in rv.data, rv.data
        self.add_vendor('odm')  # 3
        self.add_user('bob@odm.com', 'odm')
        rv = self.app.post('/lvfs/vendor/3/modify_by_admin', data={}, follow_redirects=True)
        assert b'Updated vendor' in rv.data, rv.data
        self.logout()

        # bob uploads to the ODM vendor
        self.login('bob@odm.com')
        self.upload(target='embargo')

        # change the ownership to 'oem' (no affiliation set up)
        rv = self.app.get('/lvfs/firmware/1/affiliation')
        assert b'Insufficient permissions to modify affiliations' in rv.data, rv.data

        # change the ownership to admin
        rv = self.app.post('/lvfs/firmware/1/affiliation/change', data=dict(
            vendor_id='1',
        ), follow_redirects=True)
        assert b'Insufficient permissions to change affiliation' in rv.data, rv.data

        # set up affiliation
        self.logout()
        self.login()
        self.add_affiliation(2, 3)
        self.logout()
        self.login('bob@odm.com', accept_agreement=False)

        # change the ownership to 'oem' (affiliation present)
        rv = self.app.get('/lvfs/firmware/1/affiliation')
        assert b'<option value="3" selected' in rv.data, rv.data
        assert b'<option value="2"' in rv.data, rv.data
        rv = self.app.post('/lvfs/firmware/1/affiliation/change', data=dict(
            vendor_id='2',
        ), follow_redirects=True)
        assert b'Changed firmware vendor' in rv.data, rv.data
        rv = self.app.get('/lvfs/firmware/1/affiliation')
        assert b'Insufficient permissions to modify affiliations' in rv.data, rv.data

        # verify remote was changed
        rv = self.app.get('/lvfs/firmware/1')
        assert b'>embargo-oem<' in rv.data, rv.data
        assert b'>embargo-odm<' not in rv.data, rv.data

    def add_affiliation(self, vendor_id_oem, vendor_id_odm):
        rv = self.app.post('/lvfs/vendor/%u/affiliation/add' % vendor_id_oem, data=dict(
            vendor_id_odm=vendor_id_odm,
        ), follow_redirects=True)
        assert b'Added affiliation' in rv.data, rv.data

    def test_affiliations(self):

        self.login()
        self.add_vendor('oem')  # 2
        self.add_user('alice@oem.com', 'oem')
        self.add_vendor('odm')  # 3
        self.add_user('bob@odm.com', 'odm')
        self.add_vendor('another-unrelated-oem')  # 4

        rv = self.app.post('/lvfs/vendor/2/modify_by_admin', data=dict(
            display_name='AliceOEM',
        ), follow_redirects=True)
        assert b'Updated vendor' in rv.data, rv.data

        rv = self.app.post('/lvfs/vendor/3/modify_by_admin', data=dict(
            display_name='BobOEM',
        ), follow_redirects=True)
        assert b'Updated vendor' in rv.data, rv.data

        # no affiliations
        rv = self.app.get('/lvfs/vendor/2/affiliations')
        assert b'No affiliations exist' in rv.data, rv.data

        # add affiliation (as admin)
        self.add_affiliation(2, 3)
        rv = self.app.get('/lvfs/vendor/2/affiliations')
        assert b'<div class="card-title">\n        BobOEM' in rv.data, rv.data

        # add duplicate (as admin)
        rv = self.app.post('/lvfs/vendor/2/affiliation/add', data=dict(
            vendor_id_odm='3',
        ), follow_redirects=True)
        assert b'Already a affiliation with that ODM' in rv.data, rv.data
        self.logout()

        # test uploading as the ODM to a vendor_id that does not exist
        self.login('bob@odm.com')
        rv = self._upload(vendor_id=999)
        assert b'Specified vendor ID not found' in rv.data, rv.data

        # test uploading as the ODM to a vendor_id without an affiliation
        rv = self._upload(vendor_id=4)
        assert b'Failed to upload file for vendor: Permission denied' in rv.data, rv.data

        # test uploading to a OEM account we have an affiliation with
        self.upload(vendor_id=2)

        # check bob can see the firmware he uploaded
        rv = self.app.get('/lvfs/firmware/1')
        assert '/downloads/' + self.checksum_upload in rv.data.decode('utf-8'), rv.data
        rv = self.app.get('/lvfs/firmware')
        assert b'ColorHug2' in rv.data, rv.data

        # check bob can change the update description and severity
        rv = self.app.post('/lvfs/component/1/modify', data=dict(
            urgency='critical',
            description='Not enough cats!',
        ), follow_redirects=True)
        assert b'Component updated' in rv.data, rv.data

        # check bob can move the firmware to the embargo remote for the *OEM*
        rv = self.app.get('/lvfs/firmware/1/target')
        assert b'/promote/embargo' in rv.data, rv.data
        rv = self.app.get('/lvfs/firmware/1/promote/embargo',
                          follow_redirects=True)
        assert b'Moved firmware' in rv.data, rv.data
        assert b'>embargo-oem<' in rv.data, rv.data
        assert b'>embargo-odm<' not in rv.data, rv.data

        # check bob can't move the firmware to stable
        rv = self.app.get('/lvfs/firmware/1/promote/stable',
                          follow_redirects=True)
        assert b'Permission denied' in rv.data, rv.data
        self.logout()

        # remove affiliation as admin
        self.login()
        rv = self.app.get('/lvfs/vendor/2/affiliation/1/delete', follow_redirects=True)
        assert b'Deleted affiliation' in rv.data, rv.data
        rv = self.app.get('/lvfs/vendor/2/affiliations')
        assert b'No affiliations exist' in rv.data, rv.data

    def test_affiliated_qa_user_cannot_promote(self):

        # add two different OEM vendors, and a shared ODM
        self.login()
        self.add_vendor('oem1')  # 2
        self.add_vendor('oem2')  # 3
        self.add_vendor('odm')   # 4
        self.add_affiliation(2, 4)
        self.add_affiliation(3, 4)

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
        rv = self.app.get('/lvfs/firmware',
                          follow_redirects=True)
        assert b'No firmware has been uploaded' in rv.data, rv.data
        rv = self.app.get('/lvfs/firmware/1/promote/testing',
                          follow_redirects=True)
        assert b'Permission denied: No QA access to 1' in rv.data, rv.data

    def test_oem_firmware_in_odm_metadata(self):

        self.login()
        self.add_vendor('oem')  # 2
        self.add_user('alice@oem.com', 'oem')
        self.add_vendor('odm')  # 3
        self.add_user('bob@odm.com', 'odm')
        self.add_vendor('another-unrelated-oem')  # 4
        self.add_affiliation(2, 3)
        rv = self.app.post('/lvfs/vendor/2/modify_by_admin', data={}, follow_redirects=True)
        assert b'Updated vendor' in rv.data, rv.data
        rv = self.app.post('/lvfs/vendor/3/modify_by_admin', data={}, follow_redirects=True)
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
        rv = self.app.get('/lvfs/vendor/2/affiliation/1/delete', follow_redirects=True)
        assert b'Deleted affiliation' in rv.data, rv.data
        rv = self.app.get('/lvfs/vendor/2/affiliations')
        assert b'No affiliations exist' in rv.data, rv.data

    def test_keywords(self):

        # upload file with keywords
        self.login()
        self.upload()

        # check keywords were copied out from the .metainfo.xml file
        rv = self.app.get('/lvfs/component/1/keywords')
        assert b'>alice<' in rv.data, rv.data
        assert b'>bob<' in rv.data, rv.data

        # add another set of keywords
        rv = self.app.post('/lvfs/component/1/keyword/add', data=dict(
            value='Clara Dave',
        ), follow_redirects=True)
        assert b'Added keywords' in rv.data, rv.data
        assert b'>clara<' in rv.data, rv.data
        assert b'>dave<' in rv.data, rv.data

        # delete one of the added keywords
        rv = self.app.get('/lvfs/component/1/keyword/3/delete', follow_redirects=True)
        assert b'Removed keyword' in rv.data, rv.data
        assert b'>alice<' in rv.data, rv.data
        assert b'>colorimeter<' not in rv.data, rv.data

    def test_device_checksums(self):

        # upload file with keywords
        self.login()
        self.upload()

        # add invalid checksums
        rv = self.app.post('/lvfs/component/1/checksum/add', data=dict(
            value='xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        ), follow_redirects=True)
        assert b'is not a recognised SHA1 or SHA256 hash' in rv.data, rv.data
        rv = self.app.post('/lvfs/component/1/checksum/add', data=dict(
            value='xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        ), follow_redirects=True)
        assert b'is not a recognised SHA1 or SHA256 hash' in rv.data, rv.data

        # add a SHA256 checksum
        rv = self.app.post('/lvfs/component/1/checksum/add', data=dict(
            value='9d72ffd950d3bedcda99a197d760457e90f3d6f2a62b30b95a488511f0dfa4ad',
        ), follow_redirects=True)
        assert b'Added device checksum' in rv.data, rv.data
        assert b'9d72ffd950d3bedcda99a197d760457e90f3d6f2a62b30b95a488511f0dfa4ad' in rv.data, rv.data

        # add the same checksum again
        rv = self.app.post('/lvfs/component/1/checksum/add', data=dict(
            value='9d72ffd950d3bedcda99a197d760457e90f3d6f2a62b30b95a488511f0dfa4ad',
        ), follow_redirects=True)
        assert b'has already been added' in rv.data, rv.data

        # add a SHA1 checksum
        rv = self.app.post('/lvfs/component/1/checksum/add', data=dict(
            value='fb6439cbda2add6c394f71b7cf955dd9a276ca5a',
        ), follow_redirects=True)
        assert b'Added device checksum' in rv.data, rv.data
        assert b'fb6439cbda2add6c394f71b7cf955dd9a276ca5a' in rv.data, rv.data


        # delete the checksum
        rv = self.app.get('/lvfs/component/1/checksum/delete/1', follow_redirects=True)
        assert b'Removed device checksum' in rv.data, rv.data
        assert b'9d72ffd950d3bedcda99a197d760457e90f3d6f2a62b30b95a488511f0dfa4ad' not in rv.data, rv.data

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
                '/vendorlist',
                '/lvfs/newaccount',
                '/lvfs/devicelist',
                '/lvfs/device/2082b5e0-7a64-478a-b1b2-e3404fab6dad',
                '/lvfs/docs/introduction',
                '/lvfs/docs/affiliates',
                '/lvfs/docs/agreement',
                '/lvfs/docs/metainfo',
                '/lvfs/docs/composite',
                '/lvfs/docs/telemetry',
                '/lvfs/news',
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
            rv = self.app.get(uri)
            assert b'favicon.ico' in rv.data, rv.data
            assert b'LVFS: Error' in rv.data, rv.data

    def test_horrible_hackers(self):

        # all these are an error when not logged in
        uris = ['/wp-login.php']
        for uri in uris:
            rv = self.app.get(uri)
            assert b'bad karma' in rv.data, rv.data

    def add_issue(self, issue_id=1, url='https://github.com/hughsie/fwupd/wiki/Arch-Linux', name='ColorHug on Fedora'):

        # create an issue
        rv = self.app.post('/lvfs/issue/add', data=dict(
            url=url,
        ), follow_redirects=True)
        assert b'Added issue' in rv.data, rv.data
        rv = self.app.get('/lvfs/issue/all')
        assert url in rv.data.decode('utf-8'), rv.data
        rv = self.app.get('/lvfs/issue/%i/details' % issue_id, follow_redirects=True)
        assert url in rv.data.decode('utf-8'), rv.data

        # modify the description
        data = {'name': name,
                'description': 'Matches updating ColorHug on Fedora'}
        rv = self.app.post('/lvfs/issue/%i/modify' % issue_id, data=data, follow_redirects=True)
        assert name in rv.data.decode('utf-8'), rv.data
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

    def _add_certificate(self, filename='contrib/client.pem'):
        with open(filename, 'rb') as fd:
            data = {
                'file': (fd, filename)
            }
            return self.app.post('/lvfs/user/certificate/add', data=data, follow_redirects=True)

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
        rv = self.app.get('/lvfs/user/certificate/remove/1', follow_redirects=True)
        assert b'Deleted certificate' in rv.data, rv.data
        rv = self.app.get('/lvfs/profile')
        assert b'5f11a237b994931bbef869bd0153235874fa8f8b' not in rv.data, rv.data

        self.logout()

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
        assert b'<!-- -1 -->' in rv.data, rv.data
        self.logout()

        # let alice create an issue
        self.login('alice@fwupd.org')
        self.add_issue(issue_id=2, name='Secret')
        self.add_issue_condition(issue_id=2)
        self.enable_issue(issue_id=2)
        rv = self.app.get('/lvfs/issue/2/priority/up', follow_redirects=True)
        assert b'<!-- 1 -->' in rv.data, rv.data
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
            self._download_firmware()

    def test_download_old_fwupd(self):

        # upload a file
        self.login()
        self.upload()

        # download with a new version of fwupd
        self._download_firmware(useragent='fwupd/1.0.5')

        # download with an old gnome-software and a new fwupd
        self._download_firmware(useragent='gnome-software/3.20.5 fwupd/1.0.5')

        # download with an old version of fwupd
        rv = self.app.get('/downloads/' + self.checksum_upload + '-hughski-colorhug2-2.0.3.cab',
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

    def test_agreement_decline(self):

        # add a user and try to upload firmware without signing the agreement
        self.login()
        self.add_user('testuser@fwupd.org')
        self.logout()
        self.login('testuser@fwupd.org')
        rv = self.app.get('/lvfs/agreement/1/decline', follow_redirects=True)
        assert b'Recorded decline of the agreement' in rv.data, rv.data
        rv = self._upload('contrib/hughski-colorhug2-2.0.3.cab', 'private')
        assert b'User has not signed legal agreement' in rv.data, rv.data

    def test_agreement_list_modify_add_delete(self):

        # get the default one
        self.login()
        rv = self.app.get('/lvfs/agreement/list')
        assert b'New agreement text' in rv.data, rv.data

        # modify the agreement
        rv = self.app.post('/lvfs/agreement/1/modify', data=dict(
            version=12345,
            text='DONOTSIGN',
        ), follow_redirects=True)
        assert b'Modified agreement' in rv.data, rv.data
        assert b'12345' in rv.data, rv.data
        assert b'DONOTSIGN' in rv.data, rv.data
        rv = self.app.get('/lvfs/agreement/list')
        assert b'12345' in rv.data, rv.data
        assert b'DONOTSIGN' in rv.data, rv.data

        # create a new one
        rv = self.app.get('/lvfs/agreement/create', follow_redirects=True)
        assert b'Created agreement' in rv.data, rv.data
        rv = self.app.get('/lvfs/agreement/list')
        assert b'New agreement text' in rv.data, rv.data

        # delete the original one
        rv = self.app.get('/lvfs/agreement/1/delete', follow_redirects=True)
        assert b'Deleted agreement' in rv.data, rv.data
        rv = self.app.get('/lvfs/agreement/list')
        assert b'DONOTSIGN' not in rv.data, rv.data

    def _get_token_from_eventlog(self, token_before):
        self.login()
        rv = self.app.get('/lvfs/eventlog/1/2')
        self.logout()
        found_token = False
        for tok in rv.data.decode('utf-8').split():
            if found_token:
                return tok
            if tok == token_before:
                found_token = True
        return None

    def test_password_recovery(self):

        # add a user, then try to recover the password
        self.login()
        self.add_user('testuser@fwupd.org')
        self.logout()

        # not logged in
        rv = self.app.get('/lvfs/user/recover', follow_redirects=True)
        assert b'Forgot your password' in rv.data, rv.data
        rv = self.app.post('/lvfs/user/recover', data=dict(
            username='NOBODY@fwupd.org',
        ), follow_redirects=True)
        assert b'Unable to recover password as no username' in rv.data, rv.data
        rv = self.app.post('/lvfs/user/recover', data=dict(
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
