#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2019 Richard Hughes <richard@hughsie.com>
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

    def test_mdsync(self):

        # upload a firmware that can receive a report
        self.login()
        self.add_namespace()
        self.upload(target='testing')

        # mark vendor as visible
        rv = self.app.post('/lvfs/vendors/1/modify_by_admin', data=dict(
            visible='1',
        ), follow_redirects=True)
        assert b'Updated vendor' in rv.data, rv.data

        # become partner to the LVFS
        rv = self.app.post('/lvfs/users/1/modify_by_admin',
                           data={'admin': '1',
                                 'qa': '1',
                                 'vendor-manager': '1',
                                 'partner': '1'},
                           follow_redirects=True)
        assert b'Updated profile' in rv.data, rv.data

        # move to stable
        self.run_cron_firmware()
        rv = self.app.get('/lvfs/firmware/1/promote/stable',
                          follow_redirects=True)
        assert b'>stable<' in rv.data, rv.data.decode()

        # get the LVFS world-view
        rv = self.app.get('/lvfs/mdsync/export')
        assert b'com.hughski.ColorHug2.firmware' in rv.data, rv.data.decode()
        assert b'com.hughski.colorhug' in rv.data, rv.data.decode()
        assert b'2.0.3' in rv.data, rv.data.decode()

        # import another world-view
        payload = """
{
    "devices": [
        {
            "appstream_id": "com.hughski.ColorHug2.firmware",
            "names": [
                "ColorHug2"
            ],
            "protocol": "com.hughski.colorhug",
            "versions": {
                "2.0.999": {
                    "component_id": 1,
                    "status": "stable"
                }
            }
        },
        {
            "appstream_id": "com.hughski.ColorHug3.firmware",
            "names": [
                "ColorHug3"
            ],
            "protocol": "org.usb.dfu",
            "vendor_id": 1,
            "versions": {
                "1.0.0": {
                    "changelog_url": "https://download.hughski.com/pccbbs/mobiles/r0suj04w.txt",
                    "date": "2019-06-14T00:00:00.000Z",
                    "release_tag": "r0suj04w",
                    "status": "testing"
                }
            }
        },
        {
            "appstream_id": "com.hughski.ColorHug4.firmware",
            "vendor_id": 1,
            "versions": {
                "1.2.3": {
                }
            }
        }
    ],
    "metadata": {
        "version": 0
    }
}
"""
        rv = self.app.post('/lvfs/mdsync/import', data=payload, follow_redirects=True)
        assert b'"success": true' in rv.data, rv.data.decode()

        # list all vendors with different world-views
        rv = self.app.get('/lvfs/mdsync/', follow_redirects=True)
        assert b'Acme Corp' in rv.data, rv.data.decode()

        # all firmware known by Acme Corp.
        rv = self.app.get('/lvfs/mdsync/1', follow_redirects=True)
        assert b'com.hughski.ColorHug2.firmware' in rv.data, rv.data.decode()
        assert b'com.hughski.ColorHug3.firmware' in rv.data, rv.data.decode()
        assert b'com.hughski.ColorHug4.firmware' in rv.data, rv.data.decode()
        assert b'download.hughski.com' in rv.data, rv.data.decode()
        assert b'/lvfs/components/1' in rv.data, rv.data.decode()

if __name__ == '__main__':
    unittest.main()
