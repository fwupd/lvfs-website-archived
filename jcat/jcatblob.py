#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2020 Richard Hughes <richard@hughsie.com>
#
# SPDX-License-Identifier: GPL-2.0+
#
# pylint: disable=too-few-public-methods

import enum
import datetime
import hashlib

class JcatBlobKind(enum.IntEnum):
    UNKNOWN = 0
    SHA256 = 1
    GPG = 2
    PKCS7 = 3

class JcatBlobFlags(enum.IntEnum):
    NONE = 0
    IS_UTF8 = 1

class JcatBlob():

    def __init__(self, kind=JcatBlobKind.UNKNOWN, data=None, flags=JcatBlobFlags.NONE):
        self.kind = kind
        self.data = data
        self.flags = flags
        self.appstream_id = None
        self.timestamp = int(datetime.datetime.utcnow().timestamp())

    def __len__(self):
        if not self.data:
            return 0
        return len(self.data)

    def __repr__(self):
        return 'JcatBlob({}:{:x})'.format(str(self.kind), len(self))

    def save(self):
        node = {}
        node['Kind'] = self.kind
        node['Flags'] = self.flags
        if self.appstream_id:
            node['AppstreamId'] = self.appstream_id
        node['Timestamp'] = self.timestamp
        node['Data'] = self.data.decode()
        return node

    def load(self, node):
        self.kind = node.get('Kind', JcatBlobKind.UNKNOWN)
        self.flags = node.get('Flags', 0)
        self.appstream_id = node.get('AppstreamId', None)
        self.timestamp = node.get('Timestamp', None)
        self.data = node.get('Data', None).encode()

    @property
    def filename_ext(self):
        if self.kind == JcatBlobKind.SHA256:
            return 'sha256'
        if self.kind == JcatBlobKind.GPG:
            return 'asc'
        if self.kind == JcatBlobKind.PKCS7:
            return 'p7b'
        return None

class JcatBlobSha256(JcatBlob):

    def __init__(self, blob):
        data = hashlib.sha256(blob).hexdigest().encode()
        JcatBlob.__init__(self, JcatBlobKind.SHA256, data)

class JcatBlobText(JcatBlob):

    def __init__(self, kind, data_str):
        JcatBlob.__init__(self, kind, data_str.encode(), JcatBlobFlags.IS_UTF8)
