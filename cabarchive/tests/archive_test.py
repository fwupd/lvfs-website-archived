#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2018 Richard Hughes <richard@hughsie.com>
#
# SPDX-License-Identifier: GPL-2.0+
#
# pylint: disable=wrong-import-position

import os
import sys
import unittest
import hashlib

# allows us to run this from the project root
sys.path.append(os.path.realpath('.'))

from cabarchive import CabArchive, CabFile, NotSupportedError

class TestCabArchive(unittest.TestCase):

    def test_checksums(self):
        with open('contrib/hughski-colorhug2-2.0.3.cab', 'rb') as f:
            cabarchive = CabArchive(f.read())
        results = {
            'firmware.bin' : 'c57c7de8f7029acc44a4bfad6efd6ab0a7092cc6',
            'firmware.inf' : 'b0cb43bfb2f55fd15a8814c5c5c7b9f2ce2f4572',
            'firmware.metainfo.xml' : 'e69b16c9d6ad67db52029f9db8f4e077d19c2558',
        }
        for fn in results:
            self.assertTrue(hashlib.sha1(cabarchive[fn].buf).hexdigest() == results[fn])

    def test_missing(self):
        with open('contrib/hughski-colorhug2-2.0.3.cab', 'rb') as f:
            cabarchive = CabArchive(f.read())
        with self.assertRaises(KeyError):
            self.assertIsNone(cabarchive['README.txt'])

    def test_invalid(self):
        with self.assertRaises(NotSupportedError):
            with open('contrib/pylint.sh', 'rb') as f:
                _ = CabArchive(f.read())

    def test_uncompressed(self):
        cabarchive = CabArchive()
        cabarchive['README.txt'] = CabFile(b'foofoofoofoofoofoofoofoo')
        cabarchive['firmware.bin'] = CabFile(b'barbarbarbarbarbarbarbar')
        buf = cabarchive.save()
        self.assertEqual(len(buf), 156)
        self.assertEqual(hashlib.sha1(buf).hexdigest(), '676654685d6b5918d68081a786ae1d4dbfeb5e01')

    def test_compressed(self):
        cabarchive = CabArchive()
        cabarchive['README.txt'] = CabFile(b'foofoofoofoofoofoofoofoo')
        cabarchive['firmware.bin'] = CabFile(b'barbarbarbarbarbarbarbar')
        buf = cabarchive.save(compress=True)
        self.assertEqual(len(buf), 122)
        self.assertEqual(hashlib.sha1(buf).hexdigest(), '74e94703c403aa93b16d01b088eb52e3a9c73288')

if __name__ == '__main__':
    unittest.main()
