#!/usr/bin/python2
# -*- coding: utf-8 -*-
#
# Copyright (C) 2015-2018 Richard Hughes <richard@hughsie.com>
# Licensed under the GNU General Public License Version 2
#
# pylint: disable=singleton-comparison

from __future__ import print_function

import os
import sys

from app.metadata import _generate_metadata_kind
from app.uploadedfile import UploadedFile
from app.views_upload import _create_fw_from_uploaded_file

if __name__ == '__main__':

    archive_dir = '.'
    metadata_fn = 'metadata.xml.gz'

    if len(sys.argv) >= 2:
        archive_dir = sys.argv[1]
    if len(sys.argv) >= 3:
        metadata_fn = sys.argv[2]

    # process all archives in directory
    fws = []
    print('Searching %s' % archive_dir)
    for fn in os.listdir(archive_dir):
        if not fn.endswith('.cab'):
            continue
        print('Processing %s...' % fn)
        ufile = UploadedFile()
        ufile.parse(os.path.basename(fn), open(fn, 'r').read())
        fw = _create_fw_from_uploaded_file(ufile)
        fws.append(fw)

    # write metadata
    print('Writing %s' % metadata_fn)
    _generate_metadata_kind(metadata_fn, fws)

    # success
    sys.exit(0)
