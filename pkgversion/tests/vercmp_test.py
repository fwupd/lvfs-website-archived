#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2019 Richard Hughes <richard@hughsie.com>
#
# SPDX-License-Identifier: GPL-2.0+
#
# pylint: disable=wrong-import-position

import os
import sys
import unittest

# allows us to run this from the project root
sys.path.append(os.path.realpath('.'))

from pkgversion import vercmp

class TestpkgVersion(unittest.TestCase):

    def test_vercmp(self):

        # same
        assert vercmp('1.2.3', '1.2.3') == 0
        assert vercmp('001.002.003', '001.002.003') == 0

        # upgrade and downgrade
        assert vercmp('1.2.3', '1.2.4') < 0
        assert vercmp('001.002.000', '001.002.009') < 0
        assert vercmp('1.2.3', '1.2.2') > 0
        assert vercmp('001.002.009', '001.002.000') > 0

        # int parsing
        assert vercmp('4.01', '4.10') < 0

        # unequal depth
        assert vercmp('1.2.3', '1.2.3.1') < 0
        assert vercmp('1.2.3.1', '1.2.4') < 0

        # mixed-alpha-numeric
        assert vercmp('1.2.3a', '1.2.3a') == 0
        assert vercmp('1.2.3a', '1.2.3b') < 0
        assert vercmp('1.2.3b', '1.2.3a') > 0

        # alpha version append
        assert vercmp('1.2.3', '1.2.3a') < 0
        assert vercmp('1.2.3a', '1.2.3') > 0

        # alpha only
        assert vercmp('alpha', 'alpha') == 0
        assert vercmp('alpha', 'beta') < 0
        assert vercmp('beta', 'alpha') > 0

        # alpha-compare
        assert vercmp('1.2a.3', '1.2a.3') == 0
        assert vercmp('1.2a.3', '1.2b.3') < 0
        assert vercmp('1.2b.3', '1.2a.3') > 0

        # tilde is all-powerful
        assert vercmp('1.2.3~rc1', '1.2.3~rc1') == 0
        assert vercmp('1.2.3~rc1', '1.2.3') < 0
        assert vercmp('1.2.3', '1.2.3~rc1') > 0
        assert vercmp('1.2.3~rc2', '1.2.3~rc1') > 0

        # invalid
        with self.assertRaises(TypeError):
            assert vercmp('1', None) is None
        with self.assertRaises(TypeError):
            assert vercmp(None, '1') is None
        with self.assertRaises(TypeError):
            assert vercmp(None, None) is None

if __name__ == '__main__':
    unittest.main()
