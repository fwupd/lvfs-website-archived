#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# Copyright (C) 2015 Richard Hughes <richard@hughsie.com>
# Licensed under the GNU General Public License Version 2
#
# pylint: disable=arguments-differ

from __future__ import print_function

import sys
import ConfigParser
import StringIO

class InfParser(ConfigParser.RawConfigParser):

    def __init__(self):
        ConfigParser.RawConfigParser.__init__(self, allow_no_value=True)

    def get(self, group, key):
        val = ConfigParser.RawConfigParser.get(self, group, key)

        # handle things in localised 'Strings'
        if val.endswith('%') and val.startswith('%'):
            val = ConfigParser.RawConfigParser.get(self, 'Strings', val[1:-1])

        # format multiline comments
        fixed = []
        for ln in val.split('\n'):

            # microsoftism
            if ln.endswith('|'):
                ln = ln[:-1].strip()

            # strip double quotes
            if ln.endswith('"') and ln.startswith('"'):
                ln = ln[1:-1]
            fixed.append(ln)

        return '\n'.join(fixed)

    def read(self, fn):
        fd = open(fn)
        self.read_data(fd.read())

    def read_data(self, contents):

        # fix registry keys to have a sane key=value structure
        contents_new = []
        for ln in contents.split('\n'):
            sect = ln.split(',')
            if len(sect) == 5:
                ln = '%s->%s=%s' % (sect[0].strip(), sect[2].strip(), sect[4].strip())
            contents_new.append(ln)

        buf = StringIO.StringIO('\n'.join(contents_new))
        self.readfp(buf)

def main():
    cfg = InfParser()
    for fn in sys.argv[1:]:
        cfg.read(fn)
        for section in cfg.sections():
            print(cfg.items(section))
        print(cfg.get("Version", "CatalogFile"))
        print(cfg.get("Version", "Provider"))
        print(cfg.get("Firmware_AddReg", "HKR->FirmwareId"))
        print(cfg.get("Firmware_AddReg", "HKR->FirmwareVersion"))
        print(cfg.get("Firmware_AddReg", "HKR->FirmwareFilename"))

if __name__ == "__main__":
    main()
