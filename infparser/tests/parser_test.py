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

# allows us to run this from the project root
sys.path.append(os.path.realpath('.'))

from infparser import InfParser

class TestInfParser(unittest.TestCase):

    def test_values(self):
        with open('infparser/tests/firmware.inf', 'r') as f:
            cfg = InfParser(f.read())
        self.assertEqual(cfg.get("Firmware_AddReg", "HKR->FirmwareId"), '{2082b5e0-7a64-478a-b1b2-e3404fab6dad}')
        self.assertEqual(cfg.get("Firmware_AddReg", "HKR->FirmwareFilename"), 'firmware.bin')
        self.assertEqual(cfg.get("Firmware_AddReg", "HKR->FirmwareVersion"), '0x0000000')

if __name__ == '__main__':
    unittest.main()
