#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2015-2018 Richard Hughes <richard@hughsie.com>
# Licensed under the GNU General Public License Version 2

import base64
import os
import hashlib

from app import app

def _qa_hash(value):
    """ Generate a salted hash of the QA group """
    salt = app.config['SECRET_VENDOR_SALT']
    return hashlib.sha1((salt + value).encode('utf-8')).hexdigest()

def _addr_hash(value):
    """ Generate a salted hash of the IP address """
    salt = app.config['SECRET_ADDR_SALT']
    return hashlib.sha1((salt + value).encode('utf-8')).hexdigest()

def _password_hash(value):
    """ Generate a salted hash of the password string """
    salt = app.config['SECRET_PASSWORD_SALT']
    return hashlib.sha1((salt + value).encode('utf-8')).hexdigest()

def _otp_hash():
    """ Generate a random OTP secret """
    return base64.b32encode(os.urandom(10)).decode('utf-8')
