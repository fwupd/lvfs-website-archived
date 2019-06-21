#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2018-2019 Richard Hughes <richard@hughsie.com>
#
# SPDX-License-Identifier: GPL-2.0+
#
# pylint: disable=wrong-import-position

import os

import gi

gi.require_version('GCab', '1.0')

from gi.repository import GCab
from gi.repository import Gio
from gi.repository import GLib

from . cabfile import CabFile

class NotSupportedError(NotImplementedError):
    pass

class CabArchive(dict):
    """An object representing a Microsoft Cab archive """

    def __init__(self, buf=None, flattern=True):
        """ Parses a MS Cabinet archive """
        dict.__init__(self)

        # load archive
        if buf:
            istream = Gio.MemoryInputStream.new_from_bytes(GLib.Bytes.new(buf))
            cfarchive = GCab.Cabinet.new()
            try:
                cfarchive.load(istream)
            except gi.repository.GLib.GError as e:
                raise NotSupportedError(e)
            cfarchive.extract(None)
            for cffolder in cfarchive.get_folders():
                for cffile in cffolder.get_files():
                    # replace win32-style backslashes
                    fn = cffile.get_name().replace('\\', '/')
                    if flattern:
                        fn = os.path.basename(fn)
                    self[fn] = CabFile(cffile.get_bytes().get_data())

    def __setitem__(self, key, val):
        assert isinstance(key, str)
        assert isinstance(val, CabFile)
        val.filename = key
        dict.__setitem__(self, key, val)

    def save(self, compress=False):
        """ Output a MS Cabinet archive to bytes """
        cfarchive = GCab.Cabinet.new()

        # add a default folder with no compress
        cffolders = GCab.Folder.new(GCab.Compression.MSZIP if compress else GCab.Compression.NONE)
        cfarchive.add_folder(cffolders)

        # add each file
        for filename, cabfile in self.items():
            cffile = GCab.File.new_with_bytes(filename, GLib.Bytes.new(cabfile.buf))
            cffolders.add_file(cffile, False)

        # export as a blob
        ostream = Gio.MemoryOutputStream.new_resizable()
        cfarchive.write_simple(ostream)
        return Gio.MemoryOutputStream.steal_as_bytes(ostream).get_data()

    def __repr__(self):
        return 'CabArchive({})'.format([str(self[cabfile]) for cabfile in self])
