#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2019 Richard Hughes <richard@hughsie.com>
# Licensed under the GNU General Public License Version 2
#
# pylint: disable=no-self-use

import tempfile
import glob
import hashlib
import os
import re
import subprocess

from app import db
from app.pluginloader import PluginBase, PluginError, PluginSettingBool, PluginSettingText
from app.models import Test, ComponentShard, ComponentShardChecksum, ComponentShardInfo

def _add_component_shards(md, files):

    # remove any old shards
    for shard in md.shards:
        db.session.delete(shard)

    # parse each EFI binary as a shard
    for fn in files:
        sections = fn.rsplit('/')
        name = sections[-1].split('.')[0]
        guid = None
        for section in reversed(sections[:-1]):
            if section.find('GUID_DEFINED') != -1:
                continue
            if section.find('COMPRESSION') != -1:
                continue
            guid = section.split('_')[1].split('.')[0].lower()
            break
        if not guid:
            continue

        shard = ComponentShard(component_id=md.component_id)
        shard.info = db.session.query(ComponentShardInfo).\
                            filter(ComponentShardInfo.guid == guid).first()
        if shard.info:
            shard.info.cnt += 1
        else:
            shard.info = ComponentShardInfo(guid, name)
        with open(fn, 'rb') as f:
            data = f.read()
            shard.blob = data

            # SHA1 is what's used by researchers, but considered broken
            csum = ComponentShardChecksum(hashlib.sha1(data).hexdigest(), 'SHA1')
            shard.checksums.append(csum)

            # SHA256 is now the best we have
            csum = ComponentShardChecksum(hashlib.sha256(data).hexdigest(), 'SHA256')
            shard.checksums.append(csum)

        # add shard to component
        md.shards.append(shard)

def _run_chipsec_on_blob(self, test, md):

    # write firmware to temp file
    cwd = tempfile.TemporaryDirectory(prefix='lvfs')
    src = tempfile.NamedTemporaryFile(mode='wb',
                                      prefix='lvfs_',
                                      suffix=".bin",
                                      dir=cwd.name,
                                      delete=False)
    src.write(md.blob)
    src.flush()

    # log file output
    log = tempfile.NamedTemporaryFile(mode='wb',
                                      prefix='lvfs_',
                                      suffix=".log",
                                      dir=cwd.name,
                                      delete=False)

    # run chipsec
    cmd = self.get_setting('chipsec_binary', required=True)
    argv = [cmd, '--no_driver', '--log', log.name, 'uefi', 'decode', src.name]
    ps = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=cwd.name)
    if ps.wait() != 0:
        raise PluginError('Failed to decode file: %s' % ps.stderr.read())

    # look for shards
    outdir = src.name + '.dir'
    files = glob.glob(outdir + '/FV/**/*.efi', recursive=True)
    if not files:
        test.add_pass('Scanned', 'No firmware volumes found')
        return
    _add_component_shards(md, files)

    # print output
    with open(log.name, 'r') as f:
        test.add_pass('Scanned', f.read())

class Plugin(PluginBase):
    def __init__(self):
        PluginBase.__init__(self)

    def name(self):
        return 'CHIPSEC'

    def summary(self):
        return 'Add firmware shards for UEFI capsules'

    def settings(self):
        s = []
        s.append(PluginSettingBool('chipsec_enabled', 'Enabled', True))
        s.append(PluginSettingText('chipsec_binary', 'CHIPSEC executable', 'chipsec_util'))
        return s

    def ensure_test_for_fw(self, fw):

        # only run for capsule updates
        require_test = False
        for md in fw.mds:
            if not md.protocol:
                continue
            if md.protocol.value == 'org.uefi.capsule':
                require_test = True

        # add if not already exists
        if require_test:
            test = fw.find_test_by_plugin_id(self.id)
            if not test:
                test = Test(self.id, waivable=True)
                fw.tests.append(test)

    def run_test_on_fw(self, test, fw):

        # run chipsec on the capsule data
        for md in fw.mds:
            if md.protocol.value != 'org.uefi.capsule':
                continue
            if not md.blob:
                continue
            _run_chipsec_on_blob(self, test, md)
        db.session.commit()
