#!/usr/bin/python2
# -*- coding: utf-8 -*-
#
# Copyright (C) 2019 Richard Hughes <richard@hughsie.com>
# Licensed under the GNU General Public License Version 2
#
# pylint: disable=no-self-use

from __future__ import print_function

import os
import requests

from app.pluginloader import PluginBase, PluginError, PluginSettingBool, PluginSettingText
from app.util import _get_settings
from app.models import Test

class Plugin(PluginBase):
    def __init__(self):
        PluginBase.__init__(self)

    def name(self):
        return 'VirusTotal Monitor'

    def summary(self):
        return 'Upload firmware to VirusTotal for false-positive detection'

    def settings(self):
        s = []
        s.append(PluginSettingBool('virustotal_enable', 'Enable scanning', True))
        s.append(PluginSettingText('virustotal_remotes', 'Upload Firmware in Remotes', 'stable,testing'))
        s.append(PluginSettingText('virustotal_api_key', 'API Key', 'DEADBEEF'))
        s.append(PluginSettingText('virustotal_uri', 'Host', 'https://www.virustotal.com/api/v3/monitor/items'))
        s.append(PluginSettingText('virustotal_user_agent', 'User Agent', 'LVFS'))
        return s

    def ensure_test_for_fw(self, fw):

        # get settings
        settings = _get_settings('virustotal_enable')
        if settings['virustotal_enable'] != 'enabled':
            return

        # is the firmware not in a correct remote
        remotes = settings['virustotal_remotes'].split(',')
        if fw.remote.name not in remotes:
            return

        # add if not already exists on any component in the firmware
        test = fw.find_test_by_plugin_id(self.id)
        if not test:
            test = Test(self.id)
            fw.tests.append(test)

    def run_test_on_fw(self, test, fw):

        # get settings
        settings = _get_settings('virustotal_enable')
        if settings['virustotal_enable'] != 'enabled':
            return

        # build the remote name
        from app import app
        fn = os.path.join(app.config['DOWNLOAD_DIR'], fw.filename)
        remote_path = fw.vendor.group_id + '/' + str(fw.firmware_id) + '/' + fw.filename[41:]

        # upload the file
        with open(fn, 'rb') as file_obj:
            headers = {}
            headers['X-Apikey'] = settings['virustotal_api_key']
            headers['User-Agent'] = settings['virustotal_user_agent']
            files = {'file': ('filepath', file_obj, 'application/octet-stream')}
            args = {'path': remote_path}
            r = requests.post(settings['virustotal_uri'], files=files, data=args, headers=headers)
            if r.status_code != 200:
                test.add_fail('Uploading', r.text)
                return

        # success
        test.add_pass('Uploaded', 'All OK')
