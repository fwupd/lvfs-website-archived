#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2018 Richard Hughes <richard@hughsie.com>
#
# SPDX-License-Identifier: GPL-2.0+
#
# pylint: disable=singleton-comparison,wrong-import-position

import os
import sys

# allows us to run this from the project root
sys.path.append(os.path.realpath('.'))

from lvfs import app
from lvfs.emails import send_email

if __name__ == '__main__':
    with app.test_request_context():
        send_email("[LVFS] Test email", 'richard@hughsie.com', 'Still working')
