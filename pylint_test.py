#!/usr/bin/python2
# -*- coding: utf-8 -*-
#
# Copyright (C) 2018 Richard Hughes <richard@hughsie.com>
# Licensed under the GNU General Public License Version 2

from __future__ import print_function

import os
import sys
import subprocess

from glob import glob

def main():

    # find python files
    filenames = [y for x in os.walk('.') for y in glob(os.path.join(x[0], '*.py'))]

    # ensure imports work
    env_safe = os.environ.copy()
    env_safe['PYTHONPATH'] = os.getcwd()
    print('Using PYTHONPATH=%s' % env_safe['PYTHONPATH'])

    # run pylint on each file, any failure is globally fatal
    rc = 0
    for fn in sorted(filenames):
        if fn.find('migrations/') != -1:
            continue
        argv = ['/usr/bin/pylint-2', '--rcfile=contrib/pylintrc', fn]
        print('Checking %s' % fn)
        ps = subprocess.Popen(argv, env=env_safe)
        if ps.wait() != 0:
            rc = 1

    return rc

if __name__ == "__main__":
    sys.exit(main())
