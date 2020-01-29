#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2018 Richard Hughes <richard@hughsie.com>
#
# SPDX-License-Identifier: GPL-2.0+
#
# pylint: disable=too-few-public-methods,no-self-use

import os
import sys

from .util import _event_log, _get_settings

class PluginError(Exception):
    pass

class PluginSettingText:

    def __init__(self, key, name, default=''):
        self.key = key
        self.name = name
        self.default = default

class PluginSettingInteger:

    def __init__(self, key, name, default=0):
        self.key = key
        self.name = name
        self.default = str(default)

class PluginSettingTextList:

    def __init__(self, key, name, default=None):
        self.key = key
        self.name = name
        if default:
            self.default = ','.join(default)
        else:
            self.default = ''

class PluginSettingBool:

    def __init__(self, key, name, default=False):
        self.key = key
        self.name = name
        if default:
            self.default = 'enabled'
        else:
            self.default = 'disabled'

class PluginBase:

    def __init__(self, plugin_id=None):
        self.id = plugin_id
        self.priority = 0
        self._setting_kvs = {}
        self.name = 'Noname Plugin'
        self.summary = 'Plugin did not set summary'
        self.order_after = []

    def settings(self):
        return []

    def get_setting(self, key, required=False):
        if not self._setting_kvs:
            self._setting_kvs = _get_settings(self.id.replace('-', '_'))
        if key not in self._setting_kvs:
            raise PluginError('No key %s' % key)
        if required and not self._setting_kvs[key]:
            raise PluginError('No value set for key %s' % key)
        return self._setting_kvs[key]

    def get_setting_bool(self, key):
        if self.get_setting(key) == 'enabled':
            return True
        return False

    def get_setting_int(self, key):
        return int(self.get_setting(key))

    @property
    def enabled(self):
        for setting in self.settings():
            if setting.name == 'Enabled':
                return self.get_setting_bool(setting.key)
        return True

    def __repr__(self):
        return "Plugin object %s" % self.id

class PluginGeneral(PluginBase):
    def __init__(self):
        PluginBase.__init__(self, 'general')
        self.name = 'General'
        self.summary = 'General server settings'

    def settings(self):
        s = []
        s.append(PluginSettingText('server_warning', 'Server Warning',
                                   'This is a test instance and may be broken at any time.'))
        s.append(PluginSettingText('firmware_baseuri', 'Firmware BaseURI',
                                   'https://fwupd.org/downloads/'))
        s.append(PluginSettingTextList('hwinfo_kinds', 'Allowed hwinfo Types', ['nvme']))
        s.append(PluginSettingInteger('default_failure_minimum', 'Report failures required to demote', 5))
        s.append(PluginSettingInteger('default_failure_percentage', 'Report failures threshold for demotion', 70))
        return s

class Pluginloader:

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
            for name in plugin.order_after:
                if name not in plugins:
                    continue
                plugin2 = plugins[name]
                if not plugin2:
                    continue
                if plugin2.priority <= plugin.priority:
                    plugin.priority = plugin2.priority + 1

        # sort by priority
        for plugin in list(plugins.values()):
            self._plugins.append(plugin)
        self._plugins.sort(key=lambda x: x.priority)

        # general item
        self._plugins.insert(0, PluginGeneral())

        # success
        self.loaded = True

    def get_by_id(self, plugin_id):
        if not self.loaded:
            self.load_plugins()
        for p in self._plugins:
            if p.id == plugin_id:
                return p
        return None

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
                if not plugin.enabled:
                    continue
                try:
                    plugin.file_modified(fn)
                except PluginError as e:
                    _event_log('Plugin %s failed for FileModifed(%s): %s' % (plugin.id, fn, str(e)))

    # an archive is being built
    def archive_sign(self, cabarchive, cabfile):
        if not self.loaded:
            self.load_plugins()
        for plugin in self._plugins:
            if hasattr(plugin, 'archive_sign'):
                if not plugin.enabled:
                    continue
                try:
                    plugin.archive_sign(cabarchive, cabfile)
                except PluginError as e:
                    _event_log('Plugin %s failed for ArchiveSign(): %s' % (plugin.id, str(e)))

    # an archive is being built
    def archive_copy(self, cabarchive, cabfile):
        if not self.loaded:
            self.load_plugins()
        for plugin in self._plugins:
            if hasattr(plugin, 'archive_copy'):
                if not plugin.enabled:
                    continue
                try:
                    plugin.archive_copy(cabarchive, cabfile)
                except PluginError as e:
                    _event_log('Plugin %s failed for archive_copy(): %s' % (plugin.id, str(e)))

    # an archive is being built
    def archive_finalize(self, cabarchive, metadata=None):
        if not self.loaded:
            self.load_plugins()
        if not metadata:
            metadata = {}
        for plugin in self._plugins:
            if hasattr(plugin, 'archive_finalize'):
                if not plugin.enabled:
                    continue
                try:
                    plugin.archive_finalize(cabarchive, metadata)
                except PluginError as e:
                    _event_log('Plugin %s failed for ArchiveFinalize(): %s' % (plugin.id, str(e)))

    # ensure an test is added for the firmware
    def ensure_test_for_fw(self, fw):
        if not self.loaded:
            self.load_plugins()
        for plugin in self._plugins:
            if not plugin.enabled:
                continue

            # allow plugins to set conditionals on ensuring
            ensure_test = False
            if hasattr(plugin, 'require_test_for_fw') or hasattr(plugin, 'require_test_for_md'):
                if hasattr(plugin, 'require_test_for_fw'):
                    if plugin.require_test_for_fw(fw):
                        ensure_test = True
                if hasattr(plugin, 'require_test_for_md'):
                    for md in fw.mds:
                        if plugin.require_test_for_md(md):
                            ensure_test = True
                            break
            else:
                # any tests without either vfunc are assumed to always run
                ensure_test = True
            if not ensure_test:
                continue
            if hasattr(plugin, 'ensure_test_for_fw'):
                try:
                    plugin.ensure_test_for_fw(fw)
                except PluginError as e:
                    _event_log('Plugin %s failed for ensure_test_for_fw(): %s' % (plugin.id, str(e)))

    # log out of all oauth providers
    def oauth_logout(self):
        if not self.loaded:
            self.load_plugins()
        for plugin in self._plugins:
            if hasattr(plugin, 'oauth_logout'):
                if not plugin.enabled:
                    continue
                try:
                    plugin.oauth_logout()
                except PluginError as e:
                    _event_log('Plugin %s failed for oauth_logout(): %s' % (plugin.id, str(e)))
