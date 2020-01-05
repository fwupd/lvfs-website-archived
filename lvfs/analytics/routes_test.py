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

    def test_views_analytics(self):

        # upload firmware and download once
        self.login()
        self.add_namespace()
        self.upload()
        self._download_firmware()
        rv = self._report(signed=True)
        assert b'Signature invalid' not in rv.data, rv.data.decode()

        # get all global analytics pages
        for uri in ['/lvfs/analytics/month',
                    '/lvfs/analytics/year',
                    '/lvfs/analytics/user_agent',
                    '/lvfs/analytics/vendor',
                    '/lvfs/analytics/search_stats']:
            rv = self.app.get(uri)
            assert b'Chart.js' in rv.data, rv.data

        # downloads
        rv = self.app.get('/lvfs/analytics/clients')
        assert b'ColorHug2 X-Device' in rv.data, rv.data

        # downloads
        rv = self.app.get('/lvfs/analytics/reports')
        assert b'failed to make /boot/efi/EFI/arch/fw' in rv.data, rv.data

if __name__ == '__main__':
    unittest.main()
