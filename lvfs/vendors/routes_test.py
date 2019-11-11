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

    def test_vendorlist(self):

        # check users can't modify the list
        rv = self.app.get('/lvfs/vendors/')
        assert b'Create a new vendor' not in rv.data, rv.data

        # check admin can
        self.login()
        rv = self.app.get('/lvfs/vendors/')
        assert b'Create a new vendor' in rv.data, rv.data

        # create new vendor
        rv = self.app.post('/lvfs/vendors/create', data=dict(group_id='testvendor'),
                           follow_redirects=True)
        assert b'Added vendor' in rv.data, rv.data
        rv = self.app.get('/lvfs/vendors/')
        assert b'testvendor' in rv.data, rv.data

        # create duplicate
        rv = self.app.post('/lvfs/vendors/create', data=dict(group_id='testvendor'),
                           follow_redirects=True)
        assert b'Group ID already exists' in rv.data, rv.data

        # show the details page
        rv = self.app.get('/lvfs/vendors/2/details')
        assert b'testvendor' in rv.data, rv.data

        # create a restriction
        rv = self.app.post('/lvfs/vendors/2/restriction/create', data=dict(value='USB:0x1234'),
                           follow_redirects=True)
        assert b'Added restriction' in rv.data, rv.data

        # show the restrictions page
        rv = self.app.get('/lvfs/vendors/2/restrictions')
        assert b'USB:0x1234' in rv.data, rv.data

        # delete a restriction
        rv = self.app.get('/lvfs/vendors/2/restriction/1/delete', follow_redirects=True)
        assert b'Deleted restriction' in rv.data, rv.data
        assert b'USB:0x1234' not in rv.data, rv.data

        # create a namespace
        rv = self.app.post('/lvfs/vendors/2/namespace/create', data=dict(value='com.dell'),
                           follow_redirects=True)
        assert b'Added namespace' in rv.data, rv.data

        # create a namespace
        rv = self.app.post('/lvfs/vendors/2/namespace/create', data=dict(value='lenovo'),
                           follow_redirects=True)
        assert b'Failed to add namespace' in rv.data, rv.data

        # show the namespaces page
        rv = self.app.get('/lvfs/vendors/2/namespaces')
        assert b'com.dell' in rv.data, rv.data

        # delete a namespace
        rv = self.app.get('/lvfs/vendors/2/namespace/1/delete', follow_redirects=True)
        assert b'Deleted namespace' in rv.data, rv.data
        assert b'com.dell' not in rv.data, rv.data

        # change some properties
        rv = self.app.post('/lvfs/vendors/2/modify_by_admin', data=dict(
            display_name='VendorName',
            plugins='dfu 1.2.3',
            description='Everything supported',
            visible=True,
            keywords='keyword',
            comments='Emailed Dave on 2018-01-14 to follow up.',
        ), follow_redirects=True)
        assert b'Updated vendor' in rv.data, rv.data
        rv = self.app.get('/lvfs/vendors/')
        assert b'testvendor' in rv.data, rv.data
        assert b'Everything supported' in rv.data, rv.data
        assert b'Emailed Dave' not in rv.data, rv.data

        # delete
        rv = self.app.get('/lvfs/vendors/999/delete', follow_redirects=True)
        assert b'No a vendor with that group ID' in rv.data, rv.data
        rv = self.app.get('/lvfs/vendors/2/delete', follow_redirects=True)
        assert b'Removed vendor' in rv.data, rv.data
        rv = self.app.get('/lvfs/vendors/')
        assert b'testvendor' not in rv.data, rv.data

    def test_affiliation_change_as_admin(self):

        # add oem and odm
        self.login()
        self.add_vendor('oem')  # 2
        self.add_user('alice@oem.com', 'oem')
        rv = self.app.post('/lvfs/vendors/2/modify_by_admin', data={}, follow_redirects=True)
        assert b'Updated vendor' in rv.data, rv.data
        self.add_vendor('odm')  # 3
        self.add_user('bob@odm.com', 'odm')
        rv = self.app.post('/lvfs/vendors/3/modify_by_admin', data={}, follow_redirects=True)
        assert b'Updated vendor' in rv.data, rv.data
        self.add_namespace(vendor_id=2)
        self.add_namespace(vendor_id=3)
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
        self.add_affiliation(3, 2, actions=['@modify-affiliation'])
        self.add_namespace(vendor_id=2)
        self.add_namespace(vendor_id=3)

        # add odm uploader and QA user
        self.add_user('alice@odm.com', 'odm')
        self.add_user('bob@odm.com', 'odm', is_qa=True)
        self.logout()

        # upload as alice
        self.login('alice@odm.com')
        self.upload(target='embargo', vendor_id=3)
        self.logout()

        # move to oem as bob
        self.login('bob@odm.com')
        rv = self.app.post('/lvfs/firmware/1/affiliation/change', data=dict(
            vendor_id='2',
        ), follow_redirects=True)
        assert b'Changed firmware vendor' in rv.data, rv.data.decode()

    def test_affiliations(self):

        self.login()
        self.add_vendor('oem')  # 2
        self.add_user('alice@oem.com', 'oem')
        self.add_vendor('odm')  # 3
        self.add_user('bob@odm.com', 'odm', is_qa=True)
        self.add_vendor('another-unrelated-oem')  # 4

        rv = self.app.post('/lvfs/vendors/2/modify_by_admin', data=dict(
            display_name='AliceOEM',
        ), follow_redirects=True)
        assert b'Updated vendor' in rv.data, rv.data

        rv = self.app.post('/lvfs/vendors/3/modify_by_admin', data=dict(
            display_name='BobOEM',
        ), follow_redirects=True)
        assert b'Updated vendor' in rv.data, rv.data

        # no affiliations
        rv = self.app.get('/lvfs/vendors/2/affiliations')
        assert b'No affiliations exist' in rv.data, rv.data

        # add affiliation (as admin)
        self.add_affiliation(2, 3)
        rv = self.app.get('/lvfs/vendors/2/affiliations')
        assert b'<div class="card-title">\n      BobOEM' in rv.data, rv.data.decode()

        # add duplicate (as admin)
        rv = self.app.post('/lvfs/vendors/2/affiliation/create', data=dict(
            vendor_id_odm='3',
        ), follow_redirects=True)
        assert b'Already a affiliation with that ODM' in rv.data, rv.data

        # add namespace
        self.add_namespace(vendor_id=2, value='com.hughski')

        # add and remove actions
        rv = self.app.get('/lvfs/vendors/2/affiliation/1/action/create/DAVE',
                          follow_redirects=True)
        assert b'Failed to add action: Expected' in rv.data, rv.data.decode()
        rv = self.app.get('/lvfs/vendors/2/affiliation/1/action/create/@test',
                          follow_redirects=True)
        assert b'Added action' in rv.data, rv.data.decode()
        rv = self.app.get('/lvfs/vendors/2/affiliation/1/action/remove/@notgoingtoexist',
                          follow_redirects=True)
        assert b'Failed to remove action: Not present' in rv.data, rv.data.decode()
        rv = self.app.get('/lvfs/vendors/2/affiliation/1/action/remove/@test',
                          follow_redirects=True)
        assert b'Removed action' in rv.data, rv.data.decode()

        self.logout()

        # test uploading as the ODM to a vendor_id that does not exist
        self.login('bob@odm.com')
        rv = self._upload(vendor_id=999)
        assert b'Specified vendor ID not found' in rv.data, rv.data

        # test uploading as the ODM to a vendor_id without an affiliation
        rv = self._upload(vendor_id=4)
        assert b'Permission denied: Failed to upload file for vendor' in rv.data, rv.data

        # test uploading to a OEM account we have an affiliation with
        self.upload(vendor_id=2)

        # check bob can see the firmware he uploaded
        rv = self.app.get('/lvfs/firmware/1')
        assert '/downloads/' + self.checksum_upload in rv.data.decode('utf-8'), rv.data
        rv = self.app.get('/lvfs/firmware/')
        assert b'ColorHug2' in rv.data, rv.data.decode()

        # check bob can change the update description and severity
        rv = self.app.post('/lvfs/components/1/modify', data=dict(
            urgency='critical',
            description='Not enough cats!',
        ), follow_redirects=True)
        assert b'Component updated' in rv.data, rv.data.decode()

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
        rv = self.app.get('/lvfs/vendors/2/affiliation/1/delete', follow_redirects=True)
        assert b'Deleted affiliation' in rv.data, rv.data
        rv = self.app.get('/lvfs/vendors/2/affiliations')
        assert b'No affiliations exist' in rv.data, rv.data

if __name__ == '__main__':
    unittest.main()
