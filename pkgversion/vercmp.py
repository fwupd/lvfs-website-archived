#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2018-2019 Richard Hughes <richard@hughsie.com>
#
# SPDX-License-Identifier: GPL-2.0+

from itertools import zip_longest

def _vercmp_char(chr1, chr2):
    if chr1 == chr2:
        return 0
    if chr1 == '~':
        return -1
    if chr2 == '~':
        return 1
    if not chr1:
        return -1
    if not chr2:
        return 1
    if ord(chr1) < ord(chr2):
        return -1
    return 1

def _vercmp_chunk(str1, str2):

    # trivial
    if str1 == str2:
        return 0

    # check each char of the chunk
    for chr1, chr2 in zip_longest(str1, str2):
        rc = _vercmp_char(chr1, chr2)
        if rc != 0:
            return rc

    # we really shouldn't get here
    return 0

def _strtoll(val):
    """ Parses a value, returning the numberic part and any string suffix """
    num_part = ''
    str_part = ''
    for char in val:
        if not str_part and char.isnumeric():
            num_part += char
            continue
        str_part += char
    if not num_part:
        return 0, str_part
    return int(num_part), str_part

def vercmp(version_a, version_b):

    # sanity check
    if not version_a or not version_b:
        raise TypeError('Version cannot be None')

    # optimisation
    if version_a == version_b:
        return 0

    # convert from hex
    if version_a.startswith('0x'):
        version_a = str(int(version_a[2:], 16))
    if version_b.startswith('0x'):
        version_b = str(int(version_b[2:], 16))

    # split into sections, and try to parse
    for split_a, split_b in zip_longest(version_a.split('.'), version_b.split('.')):

        # we lost or gained a dot
        if not split_a:
            return -1
        if not split_b:
            return 1

        # compare integers if simple
        ver_a, str_a = _strtoll(split_a)
        ver_b, str_b = _strtoll(split_b)
        if ver_a < ver_b:
            return -1
        if ver_a > ver_b:
            return 1

        # compare strings
        for chr1, chr2 in zip_longest(str_a, str_b):
            rc = _vercmp_char(chr1, chr2)
            if rc < 0:
                return -1
            if rc > 0:
                return 1

    # we really shouldn't get here
    return 0
