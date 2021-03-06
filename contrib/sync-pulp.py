#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright (C) 2020 Richard Hughes <richard@hughsie.com>
#
# SPDX-License-Identifier: GPL-2.0+
#
# pylint: disable=too-few-public-methods
#
# The machine that runs this script must have the 'requests' module installed,
# for example `yum install -y python-requests`

import os
import hashlib
import sys
import posixpath

import requests

# Python 2.x compat
try:
    FileNotFoundError
except NameError:
    FileNotFoundError = IOError # pylint: disable=redefined-builtin


class Pulp:
    def __init__(self, url):
        self.url = url
        self.manifest = 'PULP_MANIFEST'
        self.useragent = os.path.basename(sys.argv[0])
        self.session = requests.Session()

    def _download_file(self, fn):

        url_fn = posixpath.join(self.url, os.path.basename(fn))
        print('Downloading {}…'.format(url_fn))
        try:
            headers = {
                'User-Agent': self.useragent,
            }
            rv = self.session.get(url_fn, headers=headers, timeout=5)
        except (
            requests.exceptions.ConnectionError,
            requests.exceptions.ReadTimeout,
        ) as e:
            print(str(e))
        else:
            with open(fn, 'wb') as f:
                f.write(rv.content)

    def _sync_file(self, fn, csum, sz):

        # prefer SHA-256 checksum
        if csum:
            try:
                with open(fn, 'rb') as f:
                    csum_fn = hashlib.sha256(f.read()).hexdigest()
            except FileNotFoundError as _:
                self._download_file(fn)
                return
            if csum_fn != csum:
                print('{} does not match checksum {}'.format(fn, csum))
                self._download_file(fn)
            return

        # fallback to size
        if sz:
            try:
                sz_fn = os.path.getsize(fn)
            except FileNotFoundError as _:
                self._download_file(fn)
                return
            if sz_fn != sz:
                print('{} does not match size {}: {}'.format(fn, sz, sz_fn))
                self._download_file(fn)
            return

    def sync(self, path):

        # check dir exists
        if not os.path.exists(path):
            print("{} does not exist".format(path))
            return 1

        # download the PULP_MANIFEST
        try:
            print('Downloading {}…'.format(self.manifest))
            url_manifest = posixpath.join(self.url, self.manifest)
            headers = {
                'User-Agent': self.useragent,
            }
            rv = self.session.get(url_manifest, headers=headers, timeout=5)
        except (
            requests.exceptions.ConnectionError,
            requests.exceptions.ReadTimeout,
        ) as e:
            print(str(e))
            return 1

        # parse into lines
        for line in rv.content.decode().split("\n"):
            try:
                fn, csum, sz = line.rsplit(",", 2)
            except ValueError as e:
                continue
            self._sync_file(os.path.join(path, fn), csum, int(sz))

        # success
        return 0


if __name__ == '__main__':

    if len(sys.argv) != 3:
        print("USAGE: URL DIR")
        sys.exit(2)

    pulp = Pulp(url=sys.argv[1])
    sys.exit(pulp.sync(sys.argv[2]))
