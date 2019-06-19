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

# allows us to run this from the project root
sys.path.append(os.path.realpath('.'))

from cabarchive import CabArchive

def main():
    for fn in sys.argv[1:]:
        with open(fn, 'rb') as f:
            for cabfile in CabArchive(f.read()):
                print(cabfile)

if __name__ == "__main__":
    main()
