#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2019 Richard Hughes <richard@hughsie.com>
# Licensed under the GNU General Public License Version 2
#
# pylint: disable=wrong-import-position

import os
import sys
import configparser

# allows us to run this from the project root
sys.path.append(os.path.realpath('.'))

from infparser import InfParser

def main():
    for fn in sys.argv[1:]:
        with open(fn) as f:
            cfg = InfParser(f.read())
        for section in cfg.sections():
            print(cfg.items(section))
        try:
            print(cfg.get("Version", "CatalogFile"))
        except configparser.NoOptionError as _:
            pass
        try:
            print(cfg.get("Version", "Provider"))
        except configparser.NoOptionError as _:
            pass
        print(cfg.get("Firmware_AddReg", "HKR->FirmwareId"))
        print(cfg.get("Firmware_AddReg", "HKR->FirmwareVersion"))
        print(cfg.get("Firmware_AddReg", "HKR->FirmwareFilename"))

if __name__ == "__main__":
    main()
