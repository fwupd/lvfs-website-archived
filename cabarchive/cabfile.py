#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2018-2019 Richard Hughes <richard@hughsie.com>
# Licensed under the GNU General Public License Version 2

class CabFile():
    def __init__(self, buf=None, filename=None):
        """ Set defaults """
        self.filename = filename
        self.buf = buf

    def __len__(self):
        if not self.buf:
            return 0
        return len(self.buf)

    def __repr__(self):
        return 'CabFile({}:{:x})'.format(self.filename, len(self.buf))
