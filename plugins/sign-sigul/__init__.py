#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2018 Richard Hughes <richard@hughsie.com>
#
# SPDX-License-Identifier: GPL-2.0+
#
# pylint: disable=no-self-use

import subprocess
import tempfile

from jcat import JcatBlobText, JcatBlobKind
from lvfs.pluginloader import PluginBase, PluginError, PluginSettingText, PluginSettingBool
from lvfs import ploader

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
        self.name = 'Sigul Signing'
        self.summary = 'GPG sign files using Sigul, a secure signing server'

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

    def metadata_sign(self, blob):

        # create the detached signature
        blob_asc = _sigul_detached_sign_data(blob,
                                             self.get_setting('sign_sigul_config_file', required=True),
                                             self.get_setting('sign_sigul_metadata_key', required=True))
        return JcatBlobText(JcatBlobKind.GPG, blob_asc)

    def archive_sign(self, blob):

        # create the detached signature
        blob_asc = _sigul_detached_sign_data(blob,
                                             self.get_setting('sign_sigul_config_file', required=True),
                                             self.get_setting('sign_sigul_firmware_key', required=True))
        return JcatBlobText(JcatBlobKind.GPG, blob_asc)
