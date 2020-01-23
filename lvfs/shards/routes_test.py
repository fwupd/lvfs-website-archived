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

    def test_plugin_uefi_extract(self):

        self.login()
        self.upload(filename='contrib/chipsec.cab', target='private')
        rv = self.app.get('/lvfs/firmware/1/tests')

        # UEFI Capsule
        assert 'HeaderSize: 0x1c' in rv.data.decode(), rv.data
        assert 'GUID: cc4cbfa9-bf9d-540b-b92b-172ce31013c1' in rv.data.decode(), rv.data

        # does not always exist
        if not os.path.exists('/usr/bin/UEFIExtract'):
            return

        # CHIPSEC -> Blocklist
        assert 'Found PFS in Zlib compressed blob' in rv.data.decode(), rv.data.decode()
        assert 'IbvExampleCertificate' in rv.data.decode(), rv.data.decode()

        # run the cron job to create the ComponentShardInfo's
        self.run_cron_stats()

        # edit a shard description
        rv = self.app.get('/lvfs/shards/')
        assert '12345678-1234-5678-1234-567812345678' in rv.data.decode(), rv.data.decode()
        rv = self.app.get('/lvfs/shards/1/details')
        rv = self.app.post('/lvfs/shards/1/modify', data=dict(
            description='Hello Dave',
        ), follow_redirects=True)
        assert b'Modified shard' in rv.data, rv.data
        assert b'Hello Dave' in rv.data, rv.data

        # view component certificates
        rv = self.app.get('/lvfs/components/1/certificates')
        assert 'Default Company Ltd' in rv.data.decode(), rv.data

        # view components
        rv = self.app.get('/lvfs/shards/1/components')
        assert 'com.dell.12345678-1234-5678-1234-567812345678' in rv.data.decode(), rv.data.decode()
        assert 'UEFI' in rv.data.decode(), rv.data.decode()

        # view checksums
        rv = self.app.get('/lvfs/shards/1/checksums')
        assert '15acb2018caa6a136ec26d629377098e6690132577e26712da59f150ca28b436' in rv.data.decode(), rv.data.decode()
        assert 'UEFI' in rv.data.decode(), rv.data.decode()
        assert '1.2.3' in rv.data.decode(), rv.data.decode()

        # view claims
        rv = self.app.get('/lvfs/shards/1/claims')
        assert 'No claims exist yet' in rv.data.decode(), rv.data.decode()

        # add claim
        rv = self.app.post('/lvfs/shards/1/claim/create', data=dict(
            checksum='DEADBEEF',
            kind='info-dave',
            value='Dave',
        ), follow_redirects=True)
        assert b'Added claim' in rv.data, rv.data.decode()

        # add claim again
        rv = self.app.post('/lvfs/shards/1/claim/create', data=dict(
            checksum='DEADBEEF',
            kind='info-bar',
            value='Baz',
        ), follow_redirects=True)
        assert b'checksum already exists' in rv.data, rv.data.decode()

        # verify it exists
        rv = self.app.get('/lvfs/shards/1/claims')
        assert 'DEADBEEF' in rv.data.decode(), rv.data.decode()
        assert 'info-dave' in rv.data.decode(), rv.data.decode()
        assert 'Dave' in rv.data.decode(), rv.data.decode()

        # delete it
        rv = self.app.get('/lvfs/shards/1/claim/1/delete', follow_redirects=True)
        assert 'No claims exist yet' in rv.data.decode(), rv.data.decode()

        # delete it again
        rv = self.app.get('/lvfs/shards/1/claim/1/delete', follow_redirects=True)
        assert 'No shard claim found' in rv.data.decode(), rv.data.decode()

        # view claims
        rv = self.app.get('/lvfs/shards/1/claims')
        assert 'No claims exist yet' in rv.data.decode(), rv.data.decode()

if __name__ == '__main__':
    unittest.main()
