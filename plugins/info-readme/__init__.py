#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2018 Richard Hughes <richard@hughsie.com>
#
# SPDX-License-Identifier: GPL-2.0+
#
# pylint: disable=no-self-use

from cabarchive import CabFile
from lvfs.pluginloader import PluginBase, PluginError, PluginSettingText, PluginSettingBool

class Plugin(PluginBase):
    def __init__(self):
        PluginBase.__init__(self)
        self.name = 'Readme'
        self.summary = 'Add a README file to the archive'

    def settings(self):
        s = []
        s.append(PluginSettingBool('info_readme_enable', 'Enabled', False))
        s.append(PluginSettingText('info_readme_filename', 'Filename',
                                   'README.txt'))
        s.append(PluginSettingText('info_readme_template', 'Template',
                                   'plugins/info-readme/template.txt'))
        return s

    def archive_finalize(self, cabarchive, metadata):

        # does the readme file already exist?
        filename = self.get_setting('info_readme_filename', required=True)
        if filename in cabarchive:
            return

        # read in the file and do substititons
        try:
            with open(self.get_setting('info_readme_template', required=True), 'rb') as f:
                template = f.read().decode('utf-8')
        except IOError as e:
            raise PluginError from e
        for key in metadata:
            template = template.replace(key, metadata[key])

        # add it to the archive
        cabarchive[filename] = CabFile(template.encode('utf-8'))
