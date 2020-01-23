#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2018 Richard Hughes <richard@hughsie.com>
#
# SPDX-License-Identifier: GPL-2.0+
#
# pylint: disable=no-self-use

from lvfs.pluginloader import PluginBase, PluginSettingBool

class Plugin(PluginBase):
    def __init__(self):
        PluginBase.__init__(self)
        self.name = 'Windows Update'
        self.summary = 'Copy files generated using Windows Update'

    def settings(self):
        s = []
        s.append(PluginSettingBool('wu_copy_enable', 'Enabled', True))
        s.append(PluginSettingBool('wu_copy_inf', 'Include .inf files', True))
        s.append(PluginSettingBool('wu_copy_cat', 'Include .cat files', True))
        return s

    def archive_copy(self, cabarchive, cabfile):
        if cabfile.filename.endswith('.inf') and self.get_setting_bool('wu_copy_inf'):
            cabarchive[cabfile.filename] = cabfile
        elif cabfile.filename.endswith('.cat') and self.get_setting_bool('wu_copy_cat'):
            cabarchive[cabfile.filename] = cabfile
