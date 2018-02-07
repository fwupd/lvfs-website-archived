#!/usr/bin/python2
# -*- coding: utf-8 -*-
#
# Copyright (C) 2018 Richard Hughes <richard@hughsie.com>
# Licensed under the GNU General Public License Version 2

from __future__ import print_function

from app.pluginloader import PluginBase, PluginError, PluginSettingText, PluginSettingBool
from app import db
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

        # get settings
        settings = db.settings.get_filtered('info_readme_')
        if settings['enable'] != 'enabled':
            return None
        if not settings['filename']:
            raise PluginError('No filename set')
        if not settings['template']:
            raise PluginError('No template set')

        # does the readme file already exist?
        if _archive_get_files_from_glob(arc, settings['filename']):
            print("archive already has %s" % settings['filename'])
            return

        # read in the file and do substititons
        try:
            template = open(settings['template'], 'rb').read()
        except IOError as e:
            raise PluginError(e)
        for key in metadata:
            template = template.replace(key, metadata[key])

        # add it to the archive
        _archive_add(arc, settings['filename'], template.encode('utf-8'))
