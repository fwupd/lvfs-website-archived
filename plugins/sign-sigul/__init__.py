#!/usr/bin/python2
# -*- coding: utf-8 -*-
#
# Copyright (C) 2018 Richard Hughes <richard@hughsie.com>
# Licensed under the GNU General Public License Version 2
#
# pylint: disable=no-self-use

from __future__ import print_function

import os
import subprocess
import tempfile

from app.pluginloader import PluginBase, PluginError, PluginSettingText, PluginSettingBool
from app import ploader
from app.util import _get_settings
from app.util import _get_basename_safe, _archive_add, _archive_get_files_from_glob

def _sigul_detached_sign_data(contents, config, key):

    # check is valid
    if not config:
        raise PluginError('No config file set')
    if not key:
        raise PluginError('No signing key set')

    # write firmware to temp file
    src = tempfile.NamedTemporaryFile(mode='wb',
                                      prefix='sigul_',
                                      suffix=".bin",
                                      dir=None,
                                      delete=True)
    src.write(contents)
    src.flush()

    # get asc file from temp file
    dst = tempfile.NamedTemporaryFile(mode='wb',
                                      prefix='sigul_',
                                      suffix=".asc",
                                      dir=None,
                                      delete=True)

    # sign
    argv = ['sigul', '--batch', '--config-file', config,
            'sign-data', '--output', dst.name, key, src.name]
    ps = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if ps.wait() != 0:
        raise PluginError('Failed to sign: %s' % ps.stderr.read())

    # read back the temp file
    return open(dst.name, 'rb').read()

class Plugin(PluginBase):
    def __init__(self):
        PluginBase.__init__(self)

    def name(self):
        return 'Sigul'

    def summary(self):
        return 'GPG sign files using Sigul, a secure signing server.'

    def settings(self):
        s = []
        s.append(PluginSettingBool('sign_sigul_enable', 'Enabled', False))
        s.append(PluginSettingText('sign_sigul_config_file', 'Client config file',
                                   '/etc/sigul/client.conf'))
        s.append(PluginSettingText('sign_sigul_firmware_key', 'Signing key for firmware',
                                   'sigul-client-cert'))
        s.append(PluginSettingText('sign_sigul_metadata_key', 'Signing key for metadata',
                                   'sigul-client-cert'))
        return s

    def _metadata_modified(self, fn):

        # plugin not enabled
        settings = _get_settings('sign_sigul')
        if settings['sign_sigul_enable'] != 'enabled':
            return

        # generate
        blob_asc = _sigul_detached_sign_data(open(fn, 'rb').read(),
                                             settings['sign_sigul_config_file'],
                                             settings['sign_sigul_metadata_key'])
        fn_asc = fn + '.asc'
        with open(fn_asc, 'w') as f:
            f.write(blob_asc)

        # inform the plugin loader
        ploader.file_modified(fn_asc)

    def file_modified(self, fn):
        if fn.endswith('.xml.gz'):
            self._metadata_modified(fn)

    def archive_sign(self, arc, firmware_cff):

        # plugin not enabled
        settings = _get_settings('sign_sigul')
        if settings['sign_sigul_enable'] != 'enabled':
            return

        # already signed
        detached_fn = _get_basename_safe(firmware_cff.get_name() + '.asc')
        if _archive_get_files_from_glob(arc, detached_fn):
            return

        # create the detached signature
        blob_asc = _sigul_detached_sign_data(firmware_cff.get_bytes().get_data(),
                                             settings['sign_sigul_config_file'],
                                             settings['sign_sigul_firmware_key'])

        # add it to the archive
        _archive_add(arc, detached_fn, blob_asc.encode('utf-8'))
