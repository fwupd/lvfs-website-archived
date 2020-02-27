#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2015-2018 Richard Hughes <richard@hughsie.com>
#
# SPDX-License-Identifier: GPL-2.0+
#
# pylint: disable=singleton-comparison

import os
import sys
import argparse

from lvfs.metadata.utils import _generate_metadata_kind
from lvfs.upload.uploadedfile import UploadedFile, MetadataInvalid

def parse_args():
    parser = argparse.ArgumentParser(description="Generate local metadata to use with fwupd")
    parser.add_argument("--archive-directory", default=".",
                        help="Local directory of CAB archives to scan")
    parser.add_argument("--basename", default="firmware",
                        help="Target system: relative directory to metadata location")
    parser.add_argument("--metadata", default="metadata.xml.gz", help="Full path to metadata")
    args = parser.parse_args()
    return args

def create_metadata(archive_dir, basename, metadata_fn):
    # process all archives in directory
    fws = []
    print('Searching %s' % archive_dir)
    for root, dirs, files in os.walk(archive_dir): #pylint: disable=unused-variable
        for filename in files:
            if not filename.endswith('.cab'):
                continue
            print('Processing %s...' % filename)
            ufile = UploadedFile()
            try:
                with open(os.path.join(root, filename), 'rb') as f:
                    ufile.parse(filename, f.read(), use_hashed_prefix=False)
            except MetadataInvalid as e:
                print('Failed to parse {}: {}'.format(filename, e))
            else:
                fws.append(ufile.fw)

    # write metadata
    print('Writing %s' % metadata_fn)
    xml = _generate_metadata_kind(fws, firmware_baseuri="%s/" % basename, local=True)
    with open(metadata_fn, 'wb') as f:
        f.write(xml)

if __name__ == '__main__':
    ARGS = parse_args()
    create_metadata(ARGS.archive_directory, ARGS.basename, ARGS.metadata)
    sys.exit(0)
