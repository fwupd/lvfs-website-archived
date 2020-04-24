#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2018-2020 Richard Hughes <richard@hughsie.com>
#
# SPDX-License-Identifier: GPL-2.0+
#
# pylint: disable=no-self-use

from PyGnuTLS.crypto import X509Certificate, X509PrivateKey, Pkcs7
from PyGnuTLS.library.constants import GNUTLS_PKCS7_INCLUDE_TIME
from PyGnuTLS.library.errors import GNUTLSError

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

        with open(self.get_setting('sign_pkcs7_certificate', required=True), "rb") as f:
            cert = X509Certificate(f.read())
        with open(self.get_setting('sign_pkcs7_privkey', required=True), "rb") as f:
            privkey = X509PrivateKey(f.read())
        pkcs7 = Pkcs7()
        try:
            pkcs7.sign(
                cert,
                privkey,
                contents,
                flags=GNUTLS_PKCS7_INCLUDE_TIME,
            )
        except GNUTLSError as e:
            raise PluginError('Failed to sign') from e
        return pkcs7.export()

    def metadata_sign(self, blob):

        # create the detached signature
        blob_p7b = self._sign_blob(blob)
        return JcatBlobText(JcatBlobKind.PKCS7, blob_p7b)

    def archive_sign(self, blob):

        # create the detached signature
        blob_p7b = self._sign_blob(blob)
        return JcatBlobText(JcatBlobKind.PKCS7, blob_p7b)
