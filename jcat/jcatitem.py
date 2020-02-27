#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2020 Richard Hughes <richard@hughsie.com>
#
# SPDX-License-Identifier: GPL-2.0+

from . jcatblob import JcatBlob

class JcatItem():

    def __init__(self, jid=None):
        self.id = jid
        self.blobs = []

    def save(self):
        node = {}
        node['Id'] = self.id
        if self.blobs:
            node['Blobs'] = []
            for blob in self.blobs:
                node['Blobs'].append(blob.save())
        return node

    def load(self, node):
        self.id = node.get('Id', None)
        if 'Blobs' in node:
            for node_c in node['Blobs']:
                blob = JcatBlob()
                blob.load(node_c)
                self.blobs.append(blob)

    def add_blob(self, blob):
        if blob in self.blobs:
            return
        self.blobs.append(blob)

    def __repr__(self):
        return 'JcatItem({})'.format(self.id)
