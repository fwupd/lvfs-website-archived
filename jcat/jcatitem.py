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
        self.alias_ids = []

    def save(self):
        node = {}
        node['Id'] = self.id
        if self.alias_ids:
            node['AliasIds'] = []
            for jid in self.alias_ids:
                node['AliasIds'].append(jid)
        if self.blobs:
            node['Blobs'] = []
            for blob in self.blobs:
                node['Blobs'].append(blob.save())
        return node

    def load(self, node):
        self.id = node.get('Id', None)
        if 'AliasIds' in node:
            for jid in node['AliasIds']:
                self.add_alias_id(jid)
        if 'Blobs' in node:
            for node_c in node['Blobs']:
                blob = JcatBlob()
                blob.load(node_c)
                self.blobs.append(blob)

    def add_blob(self, blob):
        if blob in self.blobs:
            return
        self.blobs.append(blob)

    def add_alias_id(self, jid):
        if jid in self.alias_ids:
            return
        self.alias_ids.append(jid)

    def __repr__(self):
        return 'JcatItem({})'.format(self.id)
