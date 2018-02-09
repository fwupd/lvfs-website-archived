#!/usr/bin/python2
# -*- coding: utf-8 -*-
#
# Copyright (C) 2018 Richard Hughes <richard@hughsie.com>
# Licensed under the GNU General Public License Version 2

from app.pluginloader import PluginBase, PluginSettingBool
from app.util import _get_settings
from app.util import _get_basename_safe, _archive_add

class Plugin(PluginBase):
    def __init__(self):
        PluginBase.__init__(self)

    def name(self):
        return 'Windows Update'

    def summary(self):
        return 'Copy files generated using Windows Update.'

    def settings(self):
        s = []
        s.append(PluginSettingBool('wu_copy_inf', 'Include .inf files', True))
        s.append(PluginSettingBool('wu_copy_cat', 'Include .cat files', True))
        return s

    def archive_copy(self, arc, firmware_cff):

        settings = _get_settings('wu_copy')
        fn = _get_basename_safe(firmware_cff.get_name())
        if fn.endswith('.inf') and settings['wu_copy_inf'] == 'enabled':
            _archive_add(arc, fn, firmware_cff.get_bytes().get_data())
        if fn.endswith('.cat') and settings['wu_copy_cat'] == 'enabled':
            _archive_add(arc, fn, firmware_cff.get_bytes().get_data())
