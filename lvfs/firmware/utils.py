#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2017-2018 Richard Hughes <richard@hughsie.com>
#
# SPDX-License-Identifier: GPL-2.0+

import os
import shutil

from flask import g

from lvfs import app, db

from lvfs.models import Remote, FirmwareEvent
from lvfs.util import _event_log

def _firmware_delete(fw):

    # find private remote
    remote = db.session.query(Remote).filter(Remote.name == 'deleted').first()
    if not remote:
        _event_log('No deleted remote')
        return

    # move file so it's no longer downloadable
    path = os.path.join(app.config['DOWNLOAD_DIR'], fw.filename)
    if os.path.exists(path):
        path_new = os.path.join(app.config['RESTORE_DIR'], fw.filename)
        shutil.move(path, path_new)

    # generate next cron run
    fw.mark_dirty()

    # mark as invalid
    fw.remote_id = remote.remote_id
    fw.events.append(FirmwareEvent(fw.remote_id, g.user.user_id))
