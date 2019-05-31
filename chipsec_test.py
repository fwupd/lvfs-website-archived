#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2019 Richard Hughes <richard@hughsie.com>
# Licensed under the GNU General Public License Version 2
#
# pylint: disable=protected-access

import csv
import datetime

import app as application   #lgtm [py/import-and-import-from]
from app import db, ploader

from app.models import Test, Firmware
from app.pluginloader import PluginError

# make compatible with Flask
app = application.app

if __name__ == '__main__':

    now = datetime.date.today()
    fn = 'chipsec-{}.csv'.format(datetime.date.isoformat(now))
    with open(fn, 'w') as csvfile:
        fieldnames = ['filename', 'vendor', 'shards', 'msg']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()

        # run chipsec on each firmware file
        plugin = ploader.get_by_id('chipsec')
        for fw in db.session.query(Firmware).order_by(Firmware.firmware_id.asc()).all():
            test = Test(None)
            if fw.is_deleted:
                continue
            if not fw.remote.is_public:
                continue
            if not plugin._require_test_for_fw(fw):
                continue
            print('Processing {}: {} for {}'.format(fw.firmware_id, fw.filename, fw.vendor.group_id))
            data = {'filename' : fw.filename,
                    'vendor' : fw.vendor.group_id}
            try:
                plugin.run_test_on_fw(test, fw)
            except PluginError as e:
                print('An exception occurred', str(e))
                data['msg'] = str(e)
            else:
                data['shards'] = len(fw.md_prio.shards)

                # capture message
                msg = []
                for attr in test.attributes:
                    msg.append(attr.title)
                data['msg'] = ','.join(msg)

                # remove the elapsed time to keep diff clean
                idx = data['msg'].find('time elapsed')
                if idx != -1:
                    data['msg'] = data['msg'][:idx].strip()

                if not len(fw.md_prio.shards):
                    print('No shards: {}'.format(data['msg']))
                else:
                    print('Got {} shards: {}'.format(len(fw.md_prio.shards), data['msg']))

            # unallocate the cached blob as it's no longer needed
            fw.blob = None
            writer.writerow(data)
