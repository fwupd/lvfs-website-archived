#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2018 Richard Hughes <richard@hughsie.com>
#
# SPDX-License-Identifier: GPL-2.0+
#
# pylint: disable=singleton-comparison

import app as application

from app.emails import send_email

# make compatible with Flask
app = application.app

if __name__ == '__main__':
    with app.test_request_context():
        send_email("[LVFS] Test email", 'richard@hughsie.com', 'Still working')
