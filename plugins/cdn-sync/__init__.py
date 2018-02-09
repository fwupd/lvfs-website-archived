#!/usr/bin/python2
# -*- coding: utf-8 -*-
#
# Copyright (C) 2018 Richard Hughes <richard@hughsie.com>
# Licensed under the GNU General Public License Version 2

from __future__ import print_function

import os
import boto3

from app.pluginloader import PluginBase, PluginError, PluginSettingText, PluginSettingBool
from app.util import _get_settings

class Plugin(PluginBase):
    def __init__(self):
        PluginBase.__init__(self)

    def order_after(self):
        return ['sign-gpg']

    def name(self):
        return 'CDN'

    def summary(self):
        return 'Sync files to an S3-compatible content delivery network.'

    def settings(self):
        s = []
        s.append(PluginSettingBool('cdn_sync_enable', 'Enabled', False))
        s.append(PluginSettingText('cdn_sync_folder', 'Folder', 'downloads'))
        s.append(PluginSettingText('cdn_sync_bucket', 'Bucket', 'lvfstestbucket'))
        s.append(PluginSettingText('cdn_sync_region', 'Region', 'us-east-1'))
        s.append(PluginSettingText('cdn_sync_username', 'Username', 'aws_access_key_id'))
        s.append(PluginSettingText('cdn_sync_password', 'Password', 'aws_secret_access_key'))
        s.append(PluginSettingText('cdn_sync_files', 'File Whitelist',
                                   'firmware.xml.gz,firmware.xml.gz.asc,"'
                                   'firmware-testing.xml.gz,firmware-testing.xml.gz.asc'))
        return s

    def file_modified(self, fn):

        # is the file in the whitelist
        settings = _get_settings('cdn_sync')
        if settings['cdn_sync_enable'] != 'enabled':
            return
        fns = settings['cdn_sync_files']
        if not fns:
            raise PluginError('No file whitelist set')
        basename = os.path.basename(fn)
        if basename not in fns.split(','):
            print('%s not in %s' % (basename, fns))
            return

        # bucket not set
        if not settings['cdn_sync_bucket']:
            raise PluginError('No bucket set')

        # upload
        try:
            key = os.path.join(settings['cdn_sync_folder'], os.path.basename(fn))
            session = boto3.Session(aws_access_key_id=settings['cdn_sync_username'],
                                    aws_secret_access_key=settings['cdn_sync_password'],
                                    region_name=settings['cdn_sync_region'])
            s3 = session.resource('s3')
            bucket = s3.Bucket(settings['cdn_sync_bucket'])
            bucket.Acl().put(ACL='public-read')
            print("uploading %s as %s" % (fn, key))
            blob = open(fn, 'rb').read()
            obj = bucket.put_object(Key=key, Body=blob)
            obj.Acl().put(ACL='public-read')
        except BaseException as e:
            raise PluginError(e)
