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
        if not md.screenshot_url and not md.release_image:
            return False
        return True

    def ensure_test_for_fw(self, fw):

        # add if not already exists
        test = fw.find_test_by_plugin_id(self.id)
        if not test:
            test = Test(plugin_id=self.id, waivable=False)
            fw.tests.append(test)

    def _cdn_mirror_file(self, test, url):

        # download
        try:
            r = requests.get(url)
            r.raise_for_status()
        except requests.exceptions.RequestException as e:
            test.add_fail('Download', str(e))
            return None

        # load as a PNG
        try:
            im = Image.open(BytesIO(r.content))
        except UnidentifiedImageError as e:
            test.add_fail('Parse', str(e))
            return None
        if im.width > 800 or im.height > 600:
            test.add_fail('Size', '{}x{} is too large'.format(im.width, im.height))
        elif im.width < 300 or im.height < 100:
            test.add_fail('Size', '{}x{} is too small'.format(im.width, im.height))

        # save to download directory
        basename = 'img-{}.png'.format(hashlib.sha256(r.content).hexdigest())
        fn = os.path.join(app.config['DOWNLOAD_DIR'], basename)
        if not os.path.isfile(fn):
            im.save(fn, "PNG")

        # set the safe URL
        settings = _get_settings('firmware')
        return os.path.join(settings['firmware_baseuri_cdn'], basename)

    def run_test_on_md(self, test, md):

        if md.screenshot_url and not md.screenshot_url_safe:
            md.screenshot_url_safe = self._cdn_mirror_file(test, md.screenshot_url)
        if md.release_image and not md.release_image_safe:
            md.release_image_safe = self._cdn_mirror_file(test, md.release_image)

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
