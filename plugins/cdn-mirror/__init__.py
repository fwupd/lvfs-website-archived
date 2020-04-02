#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2019 Richard Hughes <richard@hughsie.com>
#
# SPDX-License-Identifier: GPL-2.0+
#
# pylint: disable=no-self-use

import os
import hashlib
from io import BytesIO
import requests
from PIL import Image, UnidentifiedImageError

from lvfs import app
from lvfs.pluginloader import PluginBase, PluginError, PluginSettingBool
from lvfs.models import Test
from lvfs.util import _get_settings

class Plugin(PluginBase):
    def __init__(self):
        PluginBase.__init__(self)
        self.name = 'CDN Mirror'
        self.summary = 'Mirror screenshots on the CDN for privacy'

    def settings(self):
        s = []
        s.append(PluginSettingBool('cdn_mirror_enable', 'Enabled', True))
        return s

    def require_test_for_md(self, md):
        if not md.screenshot_url:
            return False
        return True

    def ensure_test_for_fw(self, fw):

        # add if not already exists
        test = fw.find_test_by_plugin_id(self.id)
        if not test:
            test = Test(plugin_id=self.id, waivable=False)
            fw.tests.append(test)

    def run_test_on_md(self, test, md):

        # download
        try:
            r = requests.get(md.screenshot_url)
            r.raise_for_status()
        except requests.exceptions.RequestException as e:
            test.add_fail('Download', str(e))
            return
        test.add_pass('Download', md.screenshot_url)

        # load as a PNG
        try:
            im = Image.open(BytesIO(r.content))
        except UnidentifiedImageError as e:
            test.add_fail('Parse', str(e))
            return
        if im.width > 600 or im.height > 400:
            test.add_fail('Size', '{}x{} is too large'.format(im.width, im.height))
        elif im.width < 300 or im.height < 100:
            test.add_fail('Size', '{}x{} is too small'.format(im.width, im.height))
        else:
            test.add_pass('Size', '{}x{}'.format(im.width, im.height))

        # save to download directory
        basename = 'img-{}.png'.format(hashlib.sha256(r.content).hexdigest())
        fn = os.path.join(app.config['DOWNLOAD_DIR'], basename)
        if not os.path.isfile(fn):
            im.save(fn, "PNG")

        # set the safe URL
        settings = _get_settings('firmware')
        md.screenshot_url_safe = os.path.join(settings['firmware_baseuri_cdn'], basename)

# run with PYTHONPATH=. ./env/bin/python3 plugins/cdn-mirror/__init__.py
if __name__ == '__main__':
    import sys
    from lvfs.models import Firmware, Component

    plugin = Plugin()
    _test = Test(plugin_id=plugin.id)
    _fw = Firmware()
    _md = Component()
    _md.screenshot_url = 'https://github.com/fwupd/8bitdo-firmware/raw/master/screenshots/FC30.png'
    _fw.mds.append(_md)
    plugin.run_test_on_md(_test, _md)
    print('new URL', _md.screenshot_url_safe)
    for attribute in _test.attributes:
        print(attribute)
