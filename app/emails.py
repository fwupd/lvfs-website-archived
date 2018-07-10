#!/usr/bin/python2
# -*- coding: utf-8 -*-
#
# Copyright (C) 2018 Richard Hughes <richard@hughsie.com>
# Licensed under the GNU General Public License Version 2

from __future__ import print_function

from flask_mail import Message

from app import app, mail

from .decorators import async
from .util import _event_log

@async
def send_async_email(app2, msg):
    with app2.app_context():
        mail.send(msg)

def send_email(subject, recipient, text_body):
    if 'MAIL_SUPPRESS_SEND' in app.config and app.config['MAIL_SUPPRESS_SEND']:
        if 'DEBUG' in app.config and app.config['DEBUG']:
            # also save the email *contents* -- which could be password...
            _event_log('Not sending email to %s: %s' % (recipient, text_body))
        else:
            _event_log('Not sending email to %s' % recipient)
        print(text_body)
        return
    msg = Message(subject, recipients=[recipient])
    msg.body = text_body
    _event_log('Sending email to %s' % recipient)
    send_async_email(app, msg)
