#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2015-2020 Richard Hughes <richard@hughsie.com>
#
# SPDX-License-Identifier: GPL-2.0+

from __future__ import print_function

import os
import sys
import time
import requests

MAX_RETRIES = 5

def _upload(session, filename):

    # open file
    try:
        f = open(filename, 'rb')
    except IOError as e:
        print('Failed to load file', str(e))
        sys.exit(1)

    # upload
    payload = {'target': 'private'}
    for _ in range(MAX_RETRIES):
        rv = session.post('/'.join([os.environ['LVFS_SERVER'], 'lvfs', 'upload']),
                          data=payload,
                          files={'file': f})
        if rv.status_code == 201:
            return
        print('failed to upload to %s: %s' % (rv.url, rv.text))
        time.sleep(30)

    # no more retries
    sys.exit(1)

def _vendor_user_add(session, vendor_id, username, display_name):

    # upload
    payload = {'username': username,
               'display_name': display_name}
    for _ in range(MAX_RETRIES):
        rv = session.post('/'.join([os.environ['LVFS_SERVER'], 'lvfs', 'vendor', vendor_id, 'user', 'add']),
                          data=payload)
        if rv.status_code == 200:
            return
        print('failed to create user using %s: %s' % (rv.url, rv.text))
        time.sleep(30)

    # no more retries
    sys.exit(1)

def _mdsync_import(session, filename):

    # import
    try:
        with open(filename, 'rb') as f:
            payload = f.read()
    except IOError as e:
        print('Failed to load file', str(e))
        sys.exit(1)
    for _ in range(MAX_RETRIES):
        rv = session.post('/'.join([os.environ['LVFS_SERVER'], 'lvfs', 'mdsync', 'import']),
                          data=payload)
        if rv.status_code == 200:
            print('imported {} successfully: {}'.format(filename, rv.text))
            return
        print('failed to import mdsync using %s: %s' % (rv.url, rv.text))
        time.sleep(30)

    # no more retries
    sys.exit(1)

def _mdsync_export(session, filename):

    # export
    for _ in range(MAX_RETRIES):
        rv = session.get('/'.join([os.environ['LVFS_SERVER'], 'lvfs', 'mdsync', 'export']))
        if rv.status_code == 400:
            try:
                with open(filename, 'w') as f:
                    f.write(rv.text)
            except IOError as e:
                print('Failed to save file', str(e))
                sys.exit(1)
            print('exported {} successfully'.format(filename))
            return
        print('failed to export mdsync: {}'.format(rv.status_code))
        time.sleep(30)

    # no more retries
    sys.exit(1)

if __name__ == '__main__':

    # check required env variables are present
    for reqd_env in ['LVFS_PASSWORD', 'LVFS_PASSWORD', 'LVFS_SERVER']:
        if not reqd_env in os.environ:
            print('Usage: %s required' % reqd_env)
            sys.exit(1)

    if len(sys.argv) < 2:
        print('Usage: %s [upload|create-user|mdsync-import|mdsync-export]' % sys.argv[0])
        sys.exit(1)

    # log in
    s = requests.Session()
    data = {'username': os.environ['LVFS_USERNAME'],
            'password': os.environ['LVFS_PASSWORD']}
    success = False
    for _ in range(MAX_RETRIES):
        r = s.post('%s/lvfs/login' % os.environ['LVFS_SERVER'], data=data)
        if r.status_code == 200:
            success = True
            break
        print('failed to login to %s: %s' % (r.url, r.text))
        time.sleep(30)

    # no more retries
    if not success:
        sys.exit(1)

    # different actions
    if sys.argv[1] == 'upload':
        if len(sys.argv) != 3:
            print('Usage: %s upload filename' % sys.argv[0])
            sys.exit(1)
        _upload(s, sys.argv[2])
    elif sys.argv[1] == 'create-user':
        if len(sys.argv) != 5:
            print('Usage: %s upload vendor_id username display_name' % sys.argv[0])
            sys.exit(1)
        _vendor_user_add(s, sys.argv[2], sys.argv[3], sys.argv[4])
    elif sys.argv[1] == 'mdsync-import':
        if len(sys.argv) != 3:
            print('Usage: %s mdsync-import filename' % sys.argv[0])
            sys.exit(1)
        _mdsync_import(s, sys.argv[2])
    elif sys.argv[1] == 'mdsync-export':
        if len(sys.argv) != 3:
            print('Usage: %s mdsync-export filename' % sys.argv[0])
            sys.exit(1)
        _mdsync_export(s, sys.argv[2])
    else:
        print('command not found!')
        sys.exit(1)

    # success
    sys.exit(0)
