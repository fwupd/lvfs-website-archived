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

    def test_updateinfo(self):

        # get the default update info from the firmware archive
        self.login()
        self.add_namespace()
        self.upload()
        rv = self.app.get('/lvfs/components/1/update')
        assert b'Work around the MCDC04 errata' in rv.data, rv.data
        assert b'value="low" selected' in rv.data, rv.data

        # edit the description and severity
        rv = self.app.post('/lvfs/components/1/modify', data=dict(
            urgency='critical',
            description='Not enough cats!',
        ), follow_redirects=True)
        assert b'Component updated' in rv.data, rv.data

        # verify the new update info
        rv = self.app.get('/lvfs/components/1/update')
        assert b'Not enough cats' in rv.data, rv.data
        assert b'value="critical" selected' in rv.data, rv.data

    def test_name_variant_suffix(self):

        # get the default update info from the firmware archive
        self.login()
        self.add_namespace()
        self.upload()

        # edit the name_variant_suffix to something contained in the <name>
        rv = self.app.post('/lvfs/components/1/modify', data=dict(
            name_variant_suffix='Pre-Release ColorHug2',
        ), follow_redirects=True)
        assert b'Component updated' in rv.data, rv.data

        # verify the new problems
        rv = self.app.get('/lvfs/firmware/1/problems')
        assert b'ColorHug2 is already part' in rv.data, rv.data.decode()

        # edit the name_variant_suffix
        rv = self.app.post('/lvfs/components/1/modify', data=dict(
            name_variant_suffix='Pre-Release',
        ), follow_redirects=True)
        assert b'Component updated' in rv.data, rv.data

        # verify the new problems
        rv = self.app.get('/lvfs/firmware/1/problems')
        assert b'ColorHug2 is already part' not in rv.data, rv.data.decode()

    def test_requires(self):

        # check existing requires were added
        self.login()
        self.add_namespace()
        self.upload()

        # check requirements were copied out from the .metainfo.xml file
        rv = self.app.get('/lvfs/components/1/requires')
        assert b'85d38fda-fc0e-5c6f-808f-076984ae7978' in rv.data, rv.data
        assert b'name="version" value="1.0.3' in rv.data, rv.data
        assert b'ge" selected' in rv.data, rv.data
        assert b'regex" selected' in rv.data, rv.data
        assert b'BOT03.0[2-9]_*' in rv.data, rv.data

        # remove the CHID requirement
        rv = self.app.post('/lvfs/components/1/requirement/delete/3', follow_redirects=True)
        assert b'Removed requirement 85d38fda-fc0e-5c6f-808f-076984ae7978' in rv.data, rv.data

        # add an invalid CHID
        rv = self.app.post('/lvfs/components/1/requirement/modify', data=dict(
            kind='hardware',
            value='NOVALIDGUID',
        ), follow_redirects=True)
        assert b'NOVALIDGUID is not a valid GUID' in rv.data, rv.data

        # add a valid CHID
        rv = self.app.post('/lvfs/components/1/requirement/modify', data=dict(
            kind='hardware',
            value='85d38fda-fc0e-5c6f-808f-076984ae7978',
        ), follow_redirects=True)
        assert b'85d38fda-fc0e-5c6f-808f-076984ae7978' in rv.data, rv.data
        assert b'Added requirement' in rv.data, rv.data

        # modify an existing requirement by adding it again
        rv = self.app.post('/lvfs/components/1/requirement/modify', data=dict(
            kind='id',
            value='org.freedesktop.fwupd',
            compare='ge',
            version='1.0.4',
        ), follow_redirects=True)
        assert b'name="version" value="1.0.4' in rv.data, rv.data
        assert b'Modified requirement' in rv.data, rv.data

        # delete a requirement by adding an 'any' comparison
        rv = self.app.post('/lvfs/components/1/requirement/modify', data=dict(
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
        self.add_namespace()
        self.upload()

        # check keywords were copied out from the .metainfo.xml file
        rv = self.app.get('/lvfs/components/1/keywords')
        assert b'>alice<' in rv.data, rv.data
        assert b'>bob<' in rv.data, rv.data

        # add another set of keywords
        rv = self.app.post('/lvfs/components/1/keyword/create', data=dict(
            value='Clara Dave',
        ), follow_redirects=True)
        assert b'Added keywords' in rv.data, rv.data
        assert b'>clara<' in rv.data, rv.data
        assert b'>dave<' in rv.data, rv.data

        # delete one of the added keywords
        rv = self.app.post('/lvfs/components/1/keyword/3/delete', follow_redirects=True)
        assert b'Removed keyword' in rv.data, rv.data
        assert b'>alice<' in rv.data, rv.data
        assert b'>colorimeter<' not in rv.data, rv.data

    def test_issues(self):

        # upload file with issues
        self.login()
        self.add_namespace()
        self.upload(filename='contrib/intelme.cab', target='private')

        # check CVEs were copied out from the .metainfo.xml file
        rv = self.app.get('/lvfs/components/1/issues')
        assert b'CVE-2016' in rv.data, rv.data.decode()
        assert b'CVE-2017' in rv.data, rv.data.decode()

        # add another set of CVEs
        rv = self.app.post('/lvfs/components/1/issue/create', data=dict(
            value='DSA-2018-000,INTEL-SA-00000,LEN-99999',
        ), follow_redirects=True)
        assert b'Added DSA-' in rv.data, rv.data.decode()
        assert b'CVE-2016' in rv.data, rv.data.decode()
        assert b'CVE-2017' in rv.data, rv.data.decode()
        assert b'DSA-2018-000' in rv.data, rv.data.decode()
        assert b'INTEL-SA-00000' in rv.data, rv.data.decode()
        assert b'LEN-99999' in rv.data, rv.data.decode()

        # delete one of the added CVEs
        rv = self.app.post('/lvfs/components/1/issue/3/delete', follow_redirects=True)
        assert b'Removed DSA-2018-000' in rv.data, rv.data.decode()
        assert b'CVE-2017' in rv.data, rv.data.decode()

        # update the description to include CVEs
        rv = self.app.post('/lvfs/components/1/modify', data=dict(
            urgency='critical',
            description='- Address security advisories INTEL-SA-00233(CVE-2018-12126, '
                        'LEN-54321, CVE-2018-12127, LEN-12345)\n'
                        '- Firmware updates to address security advisory INTEL-SA-00213',
        ), follow_redirects=True)
        assert b'Component updated' in rv.data, rv.data

        # check there is a problem
        rv = self.app.get('/lvfs/firmware/1/problems')
        assert b'CVEs in update description' in rv.data, rv.data.decode()

        # autoimport the CVEs
        rv = self.app.get('/lvfs/components/1/issue/autoimport', follow_redirects=True)
        assert b'Added 6 issues' in rv.data, rv.data.decode()
        rv = self.app.get('/lvfs/firmware/1/problems')
        assert b'CVEs in update description' not in rv.data, rv.data.decode()
        rv = self.app.get('/lvfs/components/1/update')
        assert b'- Address security advisories\n' +\
               b'- Firmware updates to address security advisory' in rv.data, rv.data.decode()

    def test_device_checksums(self):

        # upload file with keywords
        self.login()
        self.add_namespace()
        self.upload()

        # add invalid checksums
        rv = self.app.post('/lvfs/components/1/checksum/create', data=dict(
            value='xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        ), follow_redirects=True)
        assert b'is not a recognised SHA1 or SHA256 hash' in rv.data, rv.data
        rv = self.app.post('/lvfs/components/1/checksum/create', data=dict(
            value='xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        ), follow_redirects=True)
        assert b'is not a recognised SHA1 or SHA256 hash' in rv.data, rv.data

        # add a SHA256 checksum
        rv = self.app.post('/lvfs/components/1/checksum/create', data=dict(
            value='9d72ffd950d3bedcda99a197d760457e90f3d6f2a62b30b95a488511f0dfa4ad',
        ), follow_redirects=True)
        assert b'Added device checksum' in rv.data, rv.data
        assert b'9d72ffd950d3bedcda99a197d760457e90f3d6f2a62b30b95a488511f0dfa4ad' in rv.data, rv.data

        # add the same checksum again
        rv = self.app.post('/lvfs/components/1/checksum/create', data=dict(
            value='9d72ffd950d3bedcda99a197d760457e90f3d6f2a62b30b95a488511f0dfa4ad',
        ), follow_redirects=True)
        assert b'has already been added' in rv.data, rv.data

        # add a SHA1 checksum
        rv = self.app.post('/lvfs/components/1/checksum/create', data=dict(
            value='fb6439cbda2add6c394f71b7cf955dd9a276ca5a',
        ), follow_redirects=True)
        assert b'Added device checksum' in rv.data, rv.data
        assert b'fb6439cbda2add6c394f71b7cf955dd9a276ca5a' in rv.data, rv.data

        # delete the checksum
        rv = self.app.post('/lvfs/components/1/checksum/delete/1', follow_redirects=True)
        assert b'Removed device checksum' in rv.data, rv.data
        assert b'9d72ffd950d3bedcda99a197d760457e90f3d6f2a62b30b95a488511f0dfa4ad' not in rv.data, rv.data

if __name__ == '__main__':
    unittest.main()
