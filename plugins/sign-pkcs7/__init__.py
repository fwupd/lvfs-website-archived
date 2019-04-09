#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2018 Richard Hughes <richard@hughsie.com>
# Licensed under the GNU General Public License Version 2
#
# pylint: disable=no-self-use

import subprocess
import tempfile

from app.pluginloader import PluginBase, PluginError, PluginSettingText, PluginSettingBool
from app import ploader
from app.util import _get_basename_safe, _archive_add, _archive_get_files_from_glob

class Plugin(PluginBase):
    def __init__(self):
        PluginBase.__init__(self)

    def name(self):
        return 'PKCS#7'

    def summary(self):
        return 'Sign files using the GnuTLS public key infrastructure.'

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
        argv = ['certtool', '--p7-detached-sign', '--p7-time',
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

    def _metadata_modified(self, fn):

        # read in the file
        with open(fn, 'rb') as fin:
            blob = fin.read()
        blob_p7b = self._sign_blob(blob)
        if not blob_p7b:
            return

        # write a new file
        fn_p7b = fn + '.asc'
        with open(fn_p7b, 'w') as f:
            f.write(blob_p7b)

        # inform the plugin loader
        ploader.file_modified(fn_p7b)

    def file_modified(self, fn):
        if fn.endswith('.xml.gz'):
            self._metadata_modified(fn)

    def archive_sign(self, arc, firmware_cff):

        # already signed
        detached_fn = _get_basename_safe(firmware_cff.get_name() + '.p7b')
        if _archive_get_files_from_glob(arc, detached_fn):
            return

        # create the detached signature
        blob = firmware_cff.get_bytes().get_data()
        blob_p7b = self._sign_blob(blob)
        if not blob_p7b:
            return

        # add it to the archive
        _archive_add(arc, detached_fn, blob_p7b.encode('utf-8'))
