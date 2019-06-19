#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2019 Richard Hughes <richard@hughsie.com>
#
# SPDX-License-Identifier: GPL-2.0+
#
# pylint: disable=no-self-use,no-member,too-few-public-methods

import os
import datetime

from pyasn1.codec.der import decoder as der_decoder
from pyasn1_modules import rfc2315
from pyasn1_modules import rfc2459

import pefile

from app import db
from app.pluginloader import PluginBase, PluginError, PluginSettingBool, PluginSettingInteger
from app.models import Test, ComponentShardCertificate

def _build_rfc2459_description(value):
    descs = []
    for val in value:
        attr_type = val[0]['type']
        attr_value = str(val[0]['value'])[2:] # prefixed with uint16 length
        if attr_type == rfc2459.id_at_countryName:
            descs.append('C=%s' % attr_value)
        elif attr_type == rfc2459.id_at_dnQualifier:
            descs.append('DN=%s' % attr_value)
        elif attr_type == rfc2459.id_at_organizationalUnitName:
            descs.append('OU=%s' % attr_value)
        elif attr_type == rfc2459.id_at_organizationName:
            descs.append('O=%s' % attr_value)
        elif attr_type == rfc2459.id_at_stateOrProvinceName:
            descs.append('ST=%s' % attr_value)
        elif attr_type == rfc2459.id_at_localityName:
            descs.append('L=%s' % attr_value)
        elif attr_type == rfc2459.id_at_commonName:
            descs.append('CN=%s' % attr_value)
        elif attr_type == rfc2459.id_at_givenName:
            descs.append('GN=%s' % attr_value)
        elif attr_type == rfc2459.id_at_surname:
            descs.append('SN=%s' % attr_value)
        elif attr_type == rfc2459.id_at_name:
            descs.append('N=%s' % attr_value)
    return ', '.join(descs)

def _extract_authenticode_tbscerts(tbscert):

    cert = ComponentShardCertificate(kind='Authenticode PKCS7')
    cert.serial_number = str(tbscert['serialNumber'])
    if 'validity' in tbscert:
        validity = tbscert['validity']
        cert.not_before = validity['notBefore']['utcTime'].asDateTime.replace(tzinfo=None)
        cert.not_after = validity['notAfter']['utcTime'].asDateTime.replace(tzinfo=None)
    issuer = tbscert['issuer']
    for value in issuer.values():
        cert.description = _build_rfc2459_description(value)
        break
    return cert

def _extract_certs_from_authenticode_blob(buf):

    contentInfo, _ = der_decoder.decode(buf, asn1Spec=rfc2315.ContentInfo())
    contentType = contentInfo.getComponentByName('contentType')
    contentInfoMap = {
        (1, 2, 840, 113549, 1, 7, 1): rfc2315.Data(),
        (1, 2, 840, 113549, 1, 7, 2): rfc2315.SignedData(),
        (1, 2, 840, 113549, 1, 7, 3): rfc2315.EnvelopedData(),
        (1, 2, 840, 113549, 1, 7, 4): rfc2315.SignedAndEnvelopedData(),
        (1, 2, 840, 113549, 1, 7, 5): rfc2315.DigestedData(),
        (1, 2, 840, 113549, 1, 7, 6): rfc2315.EncryptedData()
    }
    content, _ = der_decoder.decode(contentInfo.getComponentByName('content'),
                                    asn1Spec=contentInfoMap[contentType])
    certs = []
    for cert in content['certificates']:
        tbscert = cert['certificate']['tbsCertificate']
        certs.append(_extract_authenticode_tbscerts(tbscert))
    for c in content['signerInfos']:
        tbscert = c['issuerAndSerialNumber']
        certs.append(_extract_authenticode_tbscerts(tbscert))
    return certs

class Plugin(PluginBase):
    def __init__(self, plugin_id=None):
        PluginBase.__init__(self, plugin_id)

    def name(self):
        return 'PE Check'

    def summary(self):
        return 'Check the portable executable file (.efi) for common problems'

    def order_after(self):
        return ['chipsec', 'intelme']

    def settings(self):
        s = []
        s.append(PluginSettingBool('pecheck_enabled', 'Enabled', True))
        s.append(PluginSettingInteger('pecheck_allowable', 'Number of years to relax failure', 3))
        return s

    def _require_test_for_md(self, md):
        if not md.protocol:
            return False
        return md.protocol.value == 'org.uefi.capsule'

    def _require_test_for_fw(self, fw):
        for md in fw.mds:
            if self._require_test_for_md(md):
                return True
        return False

    def ensure_test_for_fw(self, fw):

        # add if not already exists
        if self._require_test_for_fw(fw):
            test = fw.find_test_by_plugin_id(self.id)
            if not test:
                test = Test(self.id, waivable=True)
                fw.tests.append(test)

    def _run_test_on_shard(self, test, shard):

        try:
            # parse PE header
            pe = pefile.PE(data=shard.blob)

            # get optional directory entry
            security = pe.OPTIONAL_HEADER.DATA_DIRECTORY[pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_SECURITY']]
            if security.VirtualAddress == 0 or security.Size == 0:
                return

            # format as a blob
            signature = pe.write()[security.VirtualAddress + 8:security.VirtualAddress + security.Size]
            if len(signature) != security.Size - 8:
                test.add_fail(shard.info.name,
                              'Unable to extract full signature, file is most likely truncated -- '\
                              'Extracted: {} bytes, expected: {} bytes'.format(len(signature), security.Size - 8))
                return
        except pefile.PEFormatError as _:
            # not a PE file, which is fine
            return

        # get all the certificates and signer
        certs = _extract_certs_from_authenticode_blob(signature)
        if not certs:
            test.add_pass(shard.info.name, 'No certificates')
            return

        # check the certs are valid, relaxing the notAfter checks by a good margin
        dtallowable = datetime.timedelta(days=self.get_setting_int('pecheck_allowable') * 365)
        for cert in certs:
            if cert.not_before and cert.not_before > shard.md.fw.timestamp:
                test.add_fail(shard.info.name,
                              'Authenticode certificate invalid before {}: {}'.\
                              format(cert.not_before, cert.description))
            elif cert.not_after and cert.not_after < shard.md.fw.timestamp - dtallowable:
                test.add_fail(shard.info.name,
                              'Authenticode certificate invalid after {}: {}'.\
                              format(cert.not_after, cert.description))

        # save certificate
        for cert in certs:
            cert.plugin_id = self.id
            cert.component_shard_id = shard.component_shard_id
            shard.certificates.append(cert)

    def run_test_on_fw(self, test, fw):

        # run analysis on each shard
        for md in fw.mds:
            if not self._require_test_for_md(md):
                continue
            for cert in md.certificates:
                if cert.plugin_id == self.id:
                    db.session.delete(cert)
            db.session.commit()
            for shard in md.shards:
                if shard.blob:
                    self._run_test_on_shard(test, shard)

# run with PYTHONPATH=. ./.env3/bin/python3 plugins/pecheck/__init__.py ./test.efi
if __name__ == '__main__':
    import sys
    from app.models import Firmware, Component, ComponentShard, ComponentShardInfo, Protocol

    for argv in sys.argv[1:]:
        print('Processing', argv)
        plugin = Plugin('pecheck')
        _test = Test(plugin.id)
        _fw = Firmware()
        _md = Component()
        _md.protocol = Protocol('org.uefi.capsule')
        _shard = ComponentShard()
        _shard.info = ComponentShardInfo(name=os.path.basename(argv))
        try:
            with open(argv, 'rb') as f:
                _shard.set_blob(f.read())
        except IsADirectoryError as _:
            continue
        _md.shards.append(_shard)
        _fw.mds.append(_md)
        plugin.run_test_on_fw(_test, _fw)
        for attribute in _test.attributes:
            print(attribute)
