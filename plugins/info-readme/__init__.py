#!/usr/bin/python2
# -*- coding: utf-8 -*-
#
# Copyright (C) 2018 Richard Hughes <richard@hughsie.com>
# Licensed under the GNU General Public License Version 2

from __future__ import print_function

import os
import datetime

from gi.repository import Gio
from gi.repository import GLib
from gi.repository import GCab

from app.pluginloader import PluginBase, PluginError, PluginSettingText, PluginSettingBool
from app import db, ploader
from app.util import _archive_get_files_from_glob

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
        folders = arc.get_folders()
        if not folders:
            print('archive has no folders')
            return
        template_bytes = GLib.Bytes.new(template.encode('utf-8'))
        readme_cff = GCab.File.new_with_bytes(settings['filename'], template_bytes)
        folders[0].add_file(readme_cff, False)
