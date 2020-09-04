#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2018 Richard Hughes <richard@hughsie.com>
#
# SPDX-License-Identifier: GPL-2.0+
#
# pylint: disable=no-self-use,line-too-long

import os
import fnmatch
import json
import requests

from lvfs.pluginloader import PluginBase, PluginError
from lvfs.pluginloader import PluginSettingText, PluginSettingBool, PluginSettingTextList

def _basename_matches_globs(basename, globs):
    for glob in globs:
        if fnmatch.fnmatch(basename, glob):
            return True
    return False

class Plugin(PluginBase):
    def __init__(self):
        PluginBase.__init__(self)
        self.name = 'CDN Purge'
        self.summary = 'Manually purge files from a content delivery network'

    def settings(self):
        s = []
        s.append(PluginSettingBool('cdn_purge_enable', 'Enabled', False))
        s.append(PluginSettingText('cdn_purge_uri', 'URI', 'https://bunnycdn.com/api/purge?url=https://lvfs.b-cdn.net/downloads/'))
        s.append(PluginSettingText('cdn_purge_accesskey', 'Accesskey', ''))
        s.append(PluginSettingTextList('cdn_purge_files', 'File Whitelist', ['*.xml.gz', '*.xml.gz.*', '*.jcat']))
        s.append(PluginSettingText('cdn_purge_method', 'Request method', 'GET'))
        return s

    def file_modified(self, fn):

        # is the file in the whitelist
        fns = self.get_setting('cdn_purge_files', required=True)
        basename = os.path.basename(fn)
        if not _basename_matches_globs(basename, fns.split(',')):
            print('%s not in %s' % (basename, fns))
            return

        # purge
        url = self.get_setting('cdn_purge_uri', required=True) + basename
        headers = {}
        accesskey = self.get_setting('cdn_purge_accesskey')
        if accesskey:
            headers['AccessKey'] = accesskey
        r = requests.request(self.get_setting('cdn_purge_method', required=True), url, headers=headers)
        if r.text:
            try:
                response = json.loads(r.text)
                if response['status'] != 'ok':
                    raise PluginError('Failed to purge metadata on CDN: ' + r.text)
            except ValueError as e:
                # BunnyCDN doesn't sent a JSON blob
                raise PluginError('Failed to purge metadata on CDN: %s' % r.text) from e
