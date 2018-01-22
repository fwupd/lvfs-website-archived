#!/usr/bin/env python2
# -*- coding: utf-8 -*-
#
# Copyright (C) 2018 Richard Hughes <richard@hughsie.com>
# Licensed under the GNU General Public License Version 2

import os
import sys

from .util import _event_log

class PluginError(Exception):
    pass

class PluginSettingText(object):

    def __init__(self, key, name):
        self.key = key
        self.name = name

class PluginBase(object):

    def __init__(self):
        self.id = None
        self.priority = 0

    def name(self):
        return 'Noname Plugin'

    def settings(self):
        return []

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
                    print "raising priority of", plugin_name
                    plugin.priority = plugin2.priority + 1

        # sort by priority
        for plugin in plugins.values():
            self._plugins.append(plugin)
        self._plugins.sort(key=lambda x: x.priority)

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
