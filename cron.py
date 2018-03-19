#!/usr/bin/python2
# -*- coding: utf-8 -*-
#
# Copyright (C) 2015-2018 Richard Hughes <richard@hughsie.com>
# Licensed under the GNU General Public License Version 2

from __future__ import print_function

import os
import sys

import app as application
from app import db, ploader

from app.models import Remote
from app.metadata import _metadata_update_targets, _metadata_update_pulp

# make compatible with Flask
app = application.app

def _regenerate_and_sign_metadata():

    # get list of dirty remotes
    remote_names = []
    remotes = []
    for r in db.session.query(Remote).all():
        if r.name == 'private':
            continue
        if r.is_dirty:
            remotes.append(r)
            remote_names.append(r.name)

    # nothing to do
    if not len(remote_names):
        return

    # update everything required
    for remote_name in remote_names:
        print('Updating: %s' % remote_name)
    _metadata_update_targets(remote_names)
    if 'stable' in remote_names:
        _metadata_update_pulp()

    # sign and sync
    download_dir = app.config['DOWNLOAD_DIR']
    for r in remotes:
        ploader.file_modified(os.path.join(download_dir, r.filename))

    # mark as no longer dirty
    for r in remotes:
        r.is_dirty = False
        db.session.commit()

    # drop caches in other sessions
    db.session.expire_all()

if __name__ == '__main__':

    if len(sys.argv) != 2 or sys.argv[1] not in ['metadata']:
        print('Usage: %s [metadata]' % sys.argv[0])
        sys.exit(1)

    # regenerate and sign metadata
    if sys.argv[1] == 'metadata':
        try:
            _regenerate_and_sign_metadata()
        except NotImplementedError as e:
            print(str(e))
            rc = 1

    sys.exit(rc)
