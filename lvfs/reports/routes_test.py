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
        rv = self.app.get('/lvfs/reports/123456')
        assert b'Report does not exist' in rv.data, rv.data

        # check the saved report
        rv = self.app.get('/lvfs/reports/1')
        assert b'UpdateState=success' in rv.data, rv.data

        # download the firmware at least once
        self._download_firmware()

        # delete the report
        rv = self.app.get('/lvfs/reports/1/delete', follow_redirects=True)
        assert b'Deleted report' in rv.data, rv.data

        # check it is really deleted
        rv = self.app.get('/lvfs/reports/1')
        assert b'Report does not exist' in rv.data, rv.data

if __name__ == '__main__':
    unittest.main()
