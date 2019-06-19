#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2018 Richard Hughes <richard@hughsie.com>
#
# SPDX-License-Identifier: GPL-2.0+

import os
import sys

from glob import glob
from pylint import epylint

def main():

    # find python files
    filenames = [y for x in os.walk('.') for y in glob(os.path.join(x[0], '*.py'))]
    rc = 0
    argv = []
    for fn in sorted(filenames):
        if fn.find('migrations/') != -1:
            continue
        if fn.find('.env') != -1:
            continue
        print('Checking %s' % fn)
        argv.append(fn)

    # run with 8 parallel tasks
    argv.append('-j 8')
    argv.append('--rcfile contrib/pylintrc')
    (pylint_stdout, pylint_stderr) = epylint.py_run(' '.join(argv), return_std=True)
    stderr = pylint_stderr.read()
    stdout = pylint_stdout.read()
    if stderr or stdout:
        print(stderr, stdout)
        rc = 1
    return rc

if __name__ == "__main__":
    sys.exit(main())
