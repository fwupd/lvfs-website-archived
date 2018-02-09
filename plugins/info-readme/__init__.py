#!/usr/bin/python2
# -*- coding: utf-8 -*-
#
# Copyright (C) 2018 Richard Hughes <richard@hughsie.com>
# Licensed under the GNU General Public License Version 2

from __future__ import print_function

import os
import datetime

from app.pluginloader import PluginBase, PluginError, PluginSettingText, PluginSettingBool
from app.models import Setting
from app.util import _archive_get_files_from_glob, _archive_add, _get_settings

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

        # get settings
        settings = _get_settings('info_readme')
        if settings['info_readme_enable'] != 'enabled':
            return None
        if not settings['info_readme_filename']:
            raise PluginError('No filename set')
        if not settings['info_readme_template']:
            raise PluginError('No template set')

        # does the readme file already exist?
        if _archive_get_files_from_glob(arc, settings['info_readme_filename']):
            print("archive already has %s" % settings['info_readme_filename'])
            return

        # read in the file and do substititons
        try:
            template = open(settings['info_readme_template'], 'rb').read()
        except IOError as e:
            raise PluginError(e)
        for key in metadata:
            template = template.replace(key, metadata[key])

        # add it to the archive
        _archive_add(arc, settings['info_readme_filename'], template.encode('utf-8'))
