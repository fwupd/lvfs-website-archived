#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2020 Richard Hughes <richard@hughsie.com>
#
# SPDX-License-Identifier: GPL-2.0+
#
# pylint: disable=wrong-import-position

import json
import gzip

from . jcatitem import JcatItem

class NotSupportedError(NotImplementedError):
    pass

class JcatFile():
    """An object representing a Jcat archive """

    def __init__(self, buf=None):
        self.version_major = 0
        self.version_minor = 1
        self.items = []
        if buf:
            self.load(buf)

    def get_item(self, jid):
        for item in self.items:
            if item.id == jid:
                return item
        item = JcatItem(jid)
        self.items.append(item)
        return item

    def add_item(self, item):
        if item in self.items:
            return
        self.items.append(item)

    def save(self):
        node = {}
        node['JcatVersionMajor'] = self.version_major
        node['JcatVersionMinor'] = self.version_minor
        if self.items:
            node['Items'] = []
            for item in self.items:
                node['Items'].append(item.save())
        return gzip.compress(json.dumps(node).encode())

    def load(self, blob):
        node = json.loads(gzip.decompress(blob))
        self.version_major = node.get('JcatVersionMajor', 0)
        self.version_minor = node.get('JcatVersionMinor', 0)
        if 'Items' in node:
            for node_c in node['Items']:
                item = JcatItem()
                item.load(node_c)
                self.items.append(item)

    def __repr__(self):
        return 'JcatFile({})'.format([str(jcatitem) for jcatitem in self.items])
