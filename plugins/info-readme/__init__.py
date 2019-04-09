#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2018 Richard Hughes <richard@hughsie.com>
# Licensed under the GNU General Public License Version 2
#
# pylint: disable=no-self-use

from app.pluginloader import PluginBase, PluginError, PluginSettingText, PluginSettingBool
from app.util import _archive_get_files_from_glob, _archive_add

class Plugin(PluginBase):
    def __init__(self):
        PluginBase.__init__(self)

    def name(self):
        return 'Readme'

    def summary(self):
        return 'Add a README file to the archive.'

    def settings(self):
        s = []
        s.append(PluginSettingBool('info_readme_enable', 'Enabled', False))
        s.append(PluginSettingText('info_readme_filename', 'Filename',
                                   'README.txt'))
        s.append(PluginSettingText('info_readme_template', 'Template',
                                   'plugins/info-readme/template.txt'))
        return s

    def archive_finalize(self, arc, metadata):

        # does the readme file already exist?
        filename = self.get_setting('info_readme_filename', required=True)
        if _archive_get_files_from_glob(arc, filename):
            print("archive already has %s" % filename)
            return

        # read in the file and do substititons
        try:
            with open(self.get_setting('info_readme_template', required=True), 'rb') as f:
                template = f.read().decode('utf-8')
        except IOError as e:
            raise PluginError(e)
        for key in metadata:
            template = template.replace(key, metadata[key])

        # add it to the archive
        _archive_add(arc, filename, template.encode('utf-8'))
