#!/usr/bin/env python2
# -*- coding: utf-8 -*-
#
# Copyright (C) 2018 Richard Hughes <richard@hughsie.com>
# Licensed under the GNU General Public License Version 2

from __future__ import print_function

import os
import sys

from .util import _event_log

class PluginError(Exception):
    pass

class PluginSettingText(object):

    def __init__(self, key, name, default=''):
        self.key = key
        self.name = name
        self.default = default

class PluginSettingBool(object):

    def __init__(self, key, name, default=False):
        self.key = key
        self.name = name
        if default:
            self.default = 'enabled'
        else:
            self.default = 'disabled'

class PluginBase(object):

    def __init__(self, plugin_id=None):
        self.id = plugin_id
        self.priority = 0

    def name(self):
        return 'Noname Plugin'

    def summary(self):
        return 'Plugin did not set summary()'

    def settings(self):
        return []

    def __repr__(self):
        return "Plugin object %s" % self.id

class PluginGeneral(PluginBase):
    def __init__(self):
        PluginBase.__init__(self, 'general')

    def name(self):
        return 'General'

    def summary(self):
        return 'General server settings.'

    def settings(self):
        s = []
        s.append(PluginSettingText('server_warning', 'Server Warning',
                                   'This is a test instance and may be broken at any time.'))
        s.append(PluginSettingText('firmware_baseuri', 'Firmware BaseURI',
                                   'https://fwupd.org/downloads/'))
        return s

class Pluginloader(object):

    def __init__(self, dirname='.'):
        self._dirname = dirname
        self._plugins = []
        self.loaded = False

    def load_plugins(self):

        if self.loaded:
            return

        plugins = {}
        sys.path.insert(0, self._dirname)
        for f in os.listdir(self._dirname):
            location = os.path.join(self._dirname, f)
            if not os.path.isdir(location):
                continue
            location_init = os.path.join(location, '__init__.py')
            if not os.path.exists(location_init):
                continue
            mod = __import__(f)
            plugins[f] = mod.Plugin()
            plugins[f].id = f
        sys.path.pop(0)

        # depsolve
        for plugin_name in plugins:
            plugin = plugins[plugin_name]
            if not hasattr(plugin, 'order_after'):
                continue
            names = plugin.order_after()
            if not names:
                continue
            for name in names:
                if name not in plugins:
                    continue
                plugin2 = plugins[name]
                if not plugin2:
                    continue
                if plugin2.priority <= plugin.priority:
                    print("raising priority of", plugin_name)
                    plugin.priority = plugin2.priority + 1

        # sort by priority
        for plugin in list(plugins.values()):
            self._plugins.append(plugin)
        self._plugins.sort(key=lambda x: x.priority)

        # general item
        self._plugins.insert(0, PluginGeneral())

        # success
        self.loaded = True

    def get_all(self):
        if not self.loaded:
            self.load_plugins()
        return self._plugins

    # a file has been modified
    def file_modified(self, fn):
        if not self.loaded:
            self.load_plugins()
        for plugin in self._plugins:
            if hasattr(plugin, 'file_modified'):
                try:
                    plugin.file_modified(fn)
                except PluginError as e:
                    _event_log('Plugin %s failed for FileModifed(%s): %s' % (plugin.id, fn, str(e)))

    # an archive is being built
    def archive_sign(self, arc, firmware_cff):
        if not self.loaded:
            self.load_plugins()
        for plugin in self._plugins:
            if hasattr(plugin, 'archive_sign'):
                try:
                    plugin.archive_sign(arc, firmware_cff)
                except PluginError as e:
                    _event_log('Plugin %s failed for ArchiveSign(): %s' % (plugin.id, str(e)))

    # an archive is being built
    def archive_copy(self, arc, firmware_cff):
        if not self.loaded:
            self.load_plugins()
        for plugin in self._plugins:
            if hasattr(plugin, 'archive_copy'):
                try:
                    plugin.archive_copy(arc, firmware_cff)
                except PluginError as e:
                    _event_log('Plugin %s failed for archive_copy(): %s' % (plugin.id, str(e)))

    # an archive is being built
    def archive_finalize(self, arc, metadata=None):
        if not self.loaded:
            self.load_plugins()
        if not metadata:
            metadata = {}
        for plugin in self._plugins:
            if hasattr(plugin, 'archive_finalize'):
                try:
                    plugin.archive_finalize(arc, metadata)
                except PluginError as e:
                    _event_log('Plugin %s failed for ArchiveFinalize(): %s' % (plugin.id, str(e)))
