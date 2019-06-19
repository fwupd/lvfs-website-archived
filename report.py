#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2015-2018 Richard Hughes <richard@hughsie.com>
#
# SPDX-License-Identifier: GPL-2.0+
#
# pylint: disable=singleton-comparison,wrong-import-position

import sys
import csv

import lvfs as application
from lvfs import db

from lvfs.models import Firmware

# make compatible with Flask
app = application.app

def _write_report_for_plugin_id(writer, plugin_id):

    fws = db.session.query(Firmware).all()
    for fw in fws:
        if fw.is_deleted:
            continue
        if not fw.remote.is_public:
            continue
        data = {'plugin': plugin_id,
                'vendor': fw.vendor.group_id,
                'model': fw.md_prio.name,
                'firmware_id': fw.firmware_id,
                'version': fw.version_display}
        for test in fw.tests:
            if test.success:
                continue
            if test.plugin_id != plugin_id:
                continue
            for attr in test.attributes:
                if attr.success:
                    continue
                data['shard'] = attr.title
                data['message'] = attr.message
                writer.writerow(data)

def _run_report_for_plugin_ids(filename, plugin_ids):
    with open(filename, 'w', newline='') as csvfile:
        fieldnames = ['plugin', 'vendor', 'model', 'version', 'shard', 'message', 'firmware_id']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for plugin_id in plugin_ids:
            _write_report_for_plugin_id(writer, plugin_id)

if __name__ == '__main__':

    # need at least one plugin ID
    if len(sys.argv) < 2:
        print('Usage: %s [pecheck] [blocklist]' % sys.argv[0])
        sys.exit(1)

    try:
        with app.test_request_context():
            _run_report_for_plugin_ids('report.csv', sys.argv[1:])
    except NotImplementedError as e:
        print(str(e))
        sys.exit(1)
