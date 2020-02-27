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

# allows us to run this from the project root
sys.path.append(os.path.realpath('.'))

from jcat import JcatFile

def main():
    for fn in sys.argv[1:]:
        with open(fn, 'rb') as f:
            for jcatitem in JcatFile(f.read()).items:
                print(jcatitem)
                for jcatblob in jcatitem.blobs:
                    print(jcatblob)

if __name__ == "__main__":
    main()
