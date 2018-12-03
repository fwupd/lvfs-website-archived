#!/usr/bin/python2
# -*- coding: utf-8 -*-
#
# Copyright (C) 2018 Richard Hughes <richard@hughsie.com>
# Licensed under the GNU General Public License Version 2
#
# pylint: disable=no-self-use,line-too-long

from __future__ import print_function

import os
import fnmatch
import json
import requests

from app.pluginloader import PluginBase, PluginError, PluginSettingText, PluginSettingBool
from app.util import _get_settings

def _basename_matches_globs(basename, globs):
    for glob in globs:
        if fnmatch.fnmatch(basename, glob):
            return True
    return False

class Plugin(PluginBase):
    def __init__(self):
        PluginBase.__init__(self)

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
        s.append(PluginSettingText('cdn_purge_method', 'Request method', 'GET'))
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
        if not _basename_matches_globs(basename, fns.split(',')):
            print('%s not in %s' % (basename, fns))
            return

        # URI not set
        if not settings['cdn_purge_uri']:
            raise PluginError('No URI set')
        if not settings['cdn_purge_method']:
            raise PluginError('No request method set')

        # purge
        url = settings['cdn_purge_uri'] + basename
        headers = {}
        if settings['cdn_purge_accesskey']:
            headers['AccessKey'] = settings['cdn_purge_accesskey']
        r = requests.request(settings['cdn_purge_method'], url, headers=headers)
        if r.text:
            try:
                response = json.loads(r.text)
                if response['status'] != 'ok':
                    raise PluginError('Failed to purge metadata on CDN: ' + r.text)
            except ValueError as e:
                # BunnyCDN doesn't sent a JSON blob
                raise PluginError('Failed to purge metadata on CDN: %s: %s' % (r.text, str(e)))
