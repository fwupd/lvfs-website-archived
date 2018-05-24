#!/usr/bin/python2
# -*- coding: utf-8 -*-
#
# Copyright (C) 2018 Richard Hughes <richard@hughsie.com>
# Licensed under the GNU General Public License Version 2
#
# pylint: disable=no-self-use,line-too-long

from __future__ import print_function

import os
import requests

from app.pluginloader import PluginBase, PluginError, PluginSettingText, PluginSettingBool
from app.util import _get_settings

class Plugin(PluginBase):
    def __init__(self):
        PluginBase.__init__(self)

    def order_after(self):
        return ['cdn-sync']

    def name(self):
        return 'CDN Purge'

    def summary(self):
        return 'Manually purge files from a content delivery network.'

    def settings(self):
        s = []
        s.append(PluginSettingBool('cdn_purge_enable', 'Enabled', False))
        s.append(PluginSettingText('cdn_purge_uri', 'URI', 'https://bunnycdn.com/api/purge?url=https://lvfs.b-cdn.net/downloads/'))
        s.append(PluginSettingText('cdn_purge_accesskey', 'Accesskey', ''))
        s.append(PluginSettingText('cdn_purge_files', 'File Whitelist', '*.xml.gz,*.xml.gz.asc'))
        return s

    def file_modified(self, fn):

        # is the file in the whitelist
        settings = _get_settings('cdn_purge')
        if settings['cdn_purge_enable'] != 'enabled':
            return
        fns = settings['cdn_purge_files']
        if not fns:
            raise PluginError('No file whitelist set')
        basename = os.path.basename(fn)
        if basename not in fns.split(','):
            print('%s not in %s' % (basename, fns))
            return

        # URI not set
        if not settings['cdn_purge_uri']:
            raise PluginError('No URI set')

        # purge
        url = settings['cdn_purge_uri'] + basename
        headers = {'AccessKey': settings['cdn_purge_accesskey']}
        r = requests.get(url, headers=headers)
        if r.text:
            raise PluginError('Failed to purge metadata on CDN: ' + r.text)
