#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2019 Richard Hughes <richard@hughsie.com>
# Licensed under the GNU General Public License Version 2
#
# pylint: disable=no-self-use

import os
import subprocess

from app.pluginloader import PluginBase, PluginError, PluginSettingBool
from app.util import _get_settings, _get_absolute_path
from app.models import Test

class Plugin(PluginBase):
    def __init__(self):
        PluginBase.__init__(self)

    def name(self):
        return 'ClamAV'

    def summary(self):
        return 'Check the firmware for trojans, viruses, malware and other malicious threats'

    def settings(self):
        s = []
        s.append(PluginSettingBool('clamav_enable', 'Enable scanning', True))
        s.append(PluginSettingBool('clamav_detect_pua', 'Detect Possibly Unwanted Applications', True))
        s.append(PluginSettingBool('clamav_use_daemon', 'Use clamd daemon', True))
        return s

    def ensure_test_for_fw(self, fw):

        # get settings
        settings = _get_settings('clamav_enable')
        if settings['clamav_enable'] != 'enabled':
            return

        # add if not already exists on any component in the firmware
        test = fw.find_test_by_plugin_id(self.id)
        if not test:
            test = Test(self.id, max_age=2592000) # one month
            fw.tests.append(test)

    def run_test_on_fw(self, test, fw):

        # get settings
        settings = _get_settings('clamav_enable')
        if settings['clamav_enable'] != 'enabled':
            return

        # get ClamAV version
        if settings['clamav_use_daemon'] == 'enabled':
            argv = ['clamdscan', '--version']
        else:
            argv = ['clamscan', '--version']
        try:
            ps = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if ps.wait() != 0:
                test.add_fail('Version', ps.stderr.read())
                return
            stdout, _ = ps.communicate()
        except OSError as e:
            test.add_fail('Scanning', str(e))
            return
        test.add_pass('Version', stdout)

        # scan cabinet archive
        fn = _get_absolute_path(fw)
        if settings['clamav_use_daemon'] == 'enabled':
            argv = ['clamdscan',
                    '--fdpass',
                    '--no-summary',
                    fn]
        else:
            argv = ['clamscan',
                    '--infected',
                    '--scan-mail=no',
                    '--phishing-scan-urls=no',
                    '--phishing-sigs=no',
                    '--scan-swf=no',
                    '--nocerts',
                    '--no-summary',
                    fn]
            if settings['clamav_detect_pua'] == 'enabled':
                argv.append('--detect-pua=yes')
        try:
            ps = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            rc = ps.wait()
            if rc == 2:
                test.add_fail('Scanning', ps.stderr.read())
                return
            stdout, _ = ps.communicate()
        except OSError as e:
            test.add_fail('Scanning', str(e))
            return

        # parse results
        if rc == 0:
            test.add_pass('Scanned', 'All OK')
        else:
            for ln in stdout.split('\n'):
                try:
                    fn, status = ln.split(': ', 2)
                except ValueError as e:
                    continue
                test.add_fail('Scanned', status)
