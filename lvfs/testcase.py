#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2018 Richard Hughes <richard@hughsie.com>
#
# SPDX-License-Identifier: GPL-2.0+
#
# pylint: disable=too-many-public-methods,line-too-long
# pylint: disable=too-many-instance-attributes,wrong-import-position,import-outside-toplevel

import os
import sys
import datetime
import unittest
import tempfile
import subprocess
import io

from contextlib import redirect_stdout

# allows us to run this from the project root
sys.path.append(os.path.realpath('.'))

class LvfsTestCase(unittest.TestCase):

    def setUp(self):

        # global checksums
        self.checksum_signed_sha1 = None
        self.checksum_signed_sha256 = None
        self.checksum_upload_sha1 = None
        self.checksum_upload_sha256 = None

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
                "WTF_CSRF_CHECK_DEFAULT = False",
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
        self.app.get('/lvfs/settings/create')
        self.app.post('/lvfs/agreements/create')
        self.app.post('/lvfs/agreements/1/accept')
        rv = self.app.post('/lvfs/settings/modify', data=dict(
            clamav_enable='disabled',
            virustotal_enable='disabled',
            uefi_extract_size_min='0',
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
        assert b'/lvfs/upload/firmware' in rv.data, rv.data
        assert b'Incorrect username' not in rv.data, rv.data
        if accept_agreement and username != 'sign-test@fwupd.org':
            rv = self.app.post('/lvfs/agreements/1/accept', follow_redirects=True)
            assert b'Recorded acceptance of the agreement' in rv.data, rv.data.decode()

    def logout(self):
        rv = self._logout()
        assert b'Logged out' in rv.data, rv.data
        assert b'/lvfs/upload/firmware' not in rv.data, rv.data

    def delete_firmware(self, firmware_id=1):
        rv = self.app.post('/lvfs/firmware/%i/delete' % firmware_id, follow_redirects=True)
        assert b'Firmware deleted' in rv.data, rv.data

    def _add_user(self, username, group_id, password):
        return self.app.post('/lvfs/users/create', data=dict(
            username=username,
            password_new=password,
            group_id=group_id,
            display_name='Generic Name',
        ), follow_redirects=True)

    def add_user(self, username='testuser@fwupd.org', group_id='testgroup',
                 password='Pa$$w0rd', is_qa=False, is_analyst=False,
                 is_vendor_manager=False, is_approved_public=False, is_robot=False,
                 is_researcher=False):
        rv = self._add_user(username, group_id, password)
        assert b'Added user' in rv.data, rv.data
        user_id_idx = rv.data.decode('utf-8').find('Added user ')
        assert user_id_idx != -1, rv.data
        user_id = int(rv.data[user_id_idx+11:user_id_idx+12])
        assert user_id != 0, rv.data
        if is_qa or is_analyst or is_vendor_manager or is_approved_public or is_robot:
            data = {'auth_type': 'local'}
            if is_qa:
                data['qa'] = '1'
            if is_analyst:
                data['analyst'] = '1'
            if is_vendor_manager:
                data['vendor-manager'] = '1'
            if is_researcher:
                data['researcher'] = '1'
            if is_approved_public:
                data['approved-public'] = '1'
            if is_robot:
                data['robot'] = '1'
            rv = self.app.post('/lvfs/users/%i/modify_by_admin' % user_id,
                               data=data, follow_redirects=True)
            assert b'Updated profile' in rv.data, rv.data.decode()

    def _upload(self, filename='contrib/hughski-colorhug2-2.0.3.cab', target='private', vendor_id=None):
        with open(filename, 'rb') as fd:
            data = {
                'target': target,
                'file': (fd, filename)
            }
            if vendor_id:
                data['vendor_id'] = vendor_id
            return self.app.post('/lvfs/upload/firmware', data=data, follow_redirects=True)

    def _ensure_checksums_from_upload(self):
        # peek into the database to get the checksums
        from lvfs import db
        from lvfs.models import Firmware
        fw = db.session.query(Firmware).first()
        self.checksum_signed_sha1 = fw.checksum_signed_sha1
        self.checksum_signed_sha256 = fw.checksum_signed_sha256
        self.checksum_upload_sha1 = fw.checksum_upload_sha1
        self.checksum_upload_sha256 = fw.checksum_upload_sha256

    def upload(self, target='private', vendor_id=None, filename='contrib/hughski-colorhug2-2.0.3.cab', fwchecks=True):
        rv = self._upload(filename, target, vendor_id)
        assert b'Uploaded file' in rv.data, rv.data.decode()
        self._ensure_checksums_from_upload()
        assert self.checksum_upload_sha256.encode('utf-8') in rv.data, rv.data
        if fwchecks:
            self.run_cron_fwchecks()

    def _download_firmware(self, useragent='fwupd/1.1.1'):
        rv = self.app.get('/downloads/' + self.checksum_upload_sha256 + '-hughski-colorhug2-2.0.3.cab',
                          environ_base={'HTTP_USER_AGENT': useragent})
        assert rv.status_code == 200, rv.status_code
        assert len(rv.data) > 10000, len(rv.data)
        assert len(rv.data) < 20000, len(rv.data)

    def run_cron_firmware(self, fn='hughski-colorhug2-2.0.3'):

        from lvfs import app
        from lvfs.firmware.utils import _sign_firmware_all
        with app.test_request_context():
            with io.StringIO() as buf, redirect_stdout(buf):
                _sign_firmware_all()
                stdout = buf.getvalue()

        assert fn in stdout, stdout
        # signing checksum has now changed
        self._ensure_checksums_from_upload()

    @staticmethod
    def run_cron_stats():

        from lvfs import app
        from lvfs.main.utils import _regenerate_metrics
        from lvfs.reports.utils import _regenerate_reports
        from lvfs.analytics.utils import _generate_stats_for_datestr
        from lvfs.models import _get_datestr_from_datetime
        with app.test_request_context():
            with io.StringIO() as buf, redirect_stdout(buf):
                _generate_stats_for_datestr(_get_datestr_from_datetime(datetime.date.today()))
                _regenerate_metrics()
                _regenerate_reports()
                stdout = buf.getvalue()

        assert 'generated' in stdout, stdout

    @staticmethod
    def run_cron_metadata(remote_ids=None):

        from lvfs import app
        from lvfs.metadata.utils import _regenerate_and_sign_metadata
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
        from lvfs.queries.utils import _query_run_all
        from lvfs.tests.utils import _test_run_all
        with app.test_request_context():
            with io.StringIO() as buf, redirect_stdout(buf):
                _test_run_all()
                _query_run_all()

    def add_vendor(self, group_id):
        rv = self.app.post('/lvfs/vendors/create', data=dict(group_id=group_id),
                           follow_redirects=True)
        assert b'Added vendor' in rv.data, rv.data

    def _report(self, updatestate=2, distro_id='fedora', checksum=None, signed=False, signature_valid=True):
        if not checksum:
            checksum = self.checksum_signed_sha1
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

    def add_affiliation(self, vendor_id_oem, vendor_id_odm, default_actions=True, actions=None):
        rv = self.app.post('/lvfs/vendors/%u/affiliation/create' % vendor_id_oem, data=dict(
            vendor_id_odm=vendor_id_odm,
        ), follow_redirects=True)
        assert b'Added affiliation' in rv.data, rv.data

        # get the affilation ID
        text = rv.data.decode()
        idx = text.find('Added affiliation')
        aff_id = text[idx + 18:idx + 19]
        assert int(aff_id) > 0
        assert int(aff_id) < 9

        # default set
        if not actions:
            actions = []
        if default_actions:
            actions.append('@modify-limit')
        for act in actions:
            rv = self.app.post('/lvfs/vendors/{}/affiliation/{}/action/create/{}'.format(vendor_id_oem, aff_id, act),
                               follow_redirects=True)
            assert b'Added action' in rv.data, rv.data.decode()

    def add_namespace(self, vendor_id=1, value='com.hughski'):
        rv = self.app.post('/lvfs/vendors/{}/namespace/create'.format(vendor_id),
                           data=dict(value=value),
                           follow_redirects=True)
        assert b'Added namespace' in rv.data, rv.data

    def add_issue(self, issue_id=1, url='https://github.com/hughsie/fwupd/wiki/Arch-Linux', name='ColorHug on Fedora'):

        # create an issue
        rv = self.app.post('/lvfs/issues/create', data=dict(
            url=url,
        ), follow_redirects=True)
        assert b'Added issue' in rv.data, rv.data
        rv = self.app.get('/lvfs/issues/')
        assert url in rv.data.decode('utf-8'), rv.data
        rv = self.app.get('/lvfs/issues/%i/details' % issue_id, follow_redirects=True)
        assert url in rv.data.decode('utf-8'), rv.data

        # modify the description
        data = {'name': name,
                'description': 'Matches updating ColorHug on Fedora'}
        rv = self.app.post('/lvfs/issues/%i/modify' % issue_id, data=data, follow_redirects=True)
        assert name in rv.data.decode('utf-8'), rv.data
        assert b'Matches updating ColorHug on Fedora' in rv.data, rv.data

    def _enable_issue(self, issue_id=1):
        return self.app.post('/lvfs/issues/%i/modify' % issue_id, data=dict(
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
        return self.app.post('/lvfs/issues/%i/condition/create' % issue_id,
                             data=data, follow_redirects=True)

    def add_issue_condition(self, issue_id=1):
        rv = self._add_issue_condition(issue_id)
        assert b'Added condition' in rv.data, rv.data

    def _add_certificate(self, filename='contrib/client.pem'):
        with open(filename, 'rb') as fd:
            data = {
                'file': (fd, filename)
            }
            return self.app.post('/lvfs/users/certificate/create', data=data, follow_redirects=True)

        self.logout()

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

if __name__ == '__main__':
    unittest.main()
