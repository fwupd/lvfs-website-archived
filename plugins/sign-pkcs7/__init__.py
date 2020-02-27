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
from lvfs import ploader, app

class Plugin(PluginBase):
    def __init__(self):
        PluginBase.__init__(self)
        self.name = 'PKCS#7 Signing'
        self.summary = 'Sign files using the GnuTLS public key infrastructure'

    def settings(self):
        s = []
        s.append(PluginSettingBool('sign_pkcs7_enable', 'Enabled', False))
        s.append(PluginSettingText('sign_pkcs7_privkey', 'Private Key',
                                   'pkcs7/fwupd.org.key'))
        s.append(PluginSettingText('sign_pkcs7_certificate', 'Certificate',
                                   'pkcs7/fwupd.org_signed.pem'))
        return s

    def _sign_blob(self, contents):

        # write firmware to temp file
        src = tempfile.NamedTemporaryFile(mode='wb',
                                          prefix='pkcs7_',
                                          suffix=".bin",
                                          dir=None,
                                          delete=True)
        src.write(contents)
        src.flush()

        # get p7b file from temp file
        dst = tempfile.NamedTemporaryFile(mode='wb',
                                          prefix='pkcs7_',
                                          suffix=".p7b",
                                          dir=None,
                                          delete=True)

        # sign
        argv = app.config['CERTTOOL'].split(' ')
        argv += ['--p7-detached-sign', '--p7-time',
                 '--load-privkey', self.get_setting('sign_pkcs7_privkey', required=True),
                 '--load-certificate', self.get_setting('sign_pkcs7_certificate', required=True),
                 '--infile', src.name,
                 '--outfile', dst.name]
        ps = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if ps.wait() != 0:
            raise PluginError('Failed to sign: %s' % ps.stderr.read())

        # read back the temp file
        with open(dst.name, 'rb') as f:
            return f.read()

    def metadata_sign(self, blob):

        # create the detached signature
        blob_p7b = self._sign_blob(blob)
        return JcatBlobText(JcatBlobKind.PKCS7, blob_p7b)

    def archive_sign(self, blob):

        # create the detached signature
        blob_p7b = self._sign_blob(blob)
        return JcatBlobText(JcatBlobKind.PKCS7, blob_p7b)
