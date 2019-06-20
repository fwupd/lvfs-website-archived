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

from lvfs.models import Component

class ComponentTestCase(unittest.TestCase):

    def test_component_sorting(self):

        md1 = Component()
        md1.version = '1.2.3'
        md2 = Component()
        md2.version = '1.2.4'
        self.assertTrue(md1 < md2)
        self.assertFalse(md2 < md1)
        self.assertTrue(md2 > md1)
        self.assertFalse(md1 > md2)

if __name__ == '__main__':
    unittest.main()
