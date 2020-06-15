#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2020 Richard Hughes <richard@hughsie.com>
#
# SPDX-License-Identifier: GPL-2.0+

import hashlib
import hmac

from lvfs import app

def _vendor_hash(vendor):
    """ Generate a HMAC of the vendor name """
    return hmac.new(key=app.config['SECRET_VENDOR_SALT'].encode(),
                    msg=vendor.group_id.encode(),
                    digestmod=hashlib.sha256).hexdigest()
