#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2020 Richard Hughes <richard@hughsie.com>
#
# SPDX-License-Identifier: GPL-2.0+
#
# pylint: disable=wrong-import-position

import os
import sys
import unittest

# allows us to run this from the project root
sys.path.append(os.path.realpath('.'))

from jcat import JcatFile, JcatItem, JcatBlob, JcatBlobKind

class TestJcatFile(unittest.TestCase):

    def test_read(self):
        with open('contrib/firmware.jcat', 'rb') as f:
            jcatfile = JcatFile(f.read())
        self.assertEqual(len(jcatfile.items), 2)
        jcatitem = jcatfile.get_item('firmware.bin')
        self.assertEqual(len(jcatitem.blobs), 2)
        jcatblob = jcatitem.blobs[1]
        self.assertEqual(jcatblob.kind, JcatBlobKind.SHA256)
        self.assertEqual(jcatblob.data, b'2577281a88fe9e2a21c7dedbf844f546158ca568f1440eef430f9b6dca499a60')

    def test_write(self):
        jcatfile = JcatFile()
        jcatitem = JcatItem('filename.bin')
        jcatfile.add_item(jcatitem)
        jcatitem.add_blob(JcatBlob(JcatBlobKind.SHA1, b'deadbeef'))
        jcatitem.add_blob(JcatBlob(JcatBlobKind.SHA256, b'deadbeef'))
        jcatitem.add_blob(JcatBlob(JcatBlobKind.GPG, b'beefdeaf'))
        with open('/tmp/firmware.jcat', 'wb') as f:
            f.write(jcatfile.save())
        self.assertEqual(jcatfile.items, [jcatitem])

if __name__ == '__main__':
    unittest.main()
