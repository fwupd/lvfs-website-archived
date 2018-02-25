#!/usr/bin/python2
# -*- coding: utf-8 -*-
#
# Copyright (C) 2015-2018 Richard Hughes <richard@hughsie.com>
# Licensed under the GNU General Public License Version 2
#
# pylint: disable=wrong-import-position,wrong-import-order

import os
import sqlalchemy

from flask import Flask, flash, render_template, message_flashed, request, Response, g
from flask_login import LoginManager
from werkzeug.local import LocalProxy

from .db import Database
from .response import SecureResponse
from .pluginloader import Pluginloader
from .util import _error_internal, _event_log

app = Flask(__name__)
if os.path.exists('app/custom.cfg'):
    app.response_class = SecureResponse
    app.config.from_pyfile('custom.cfg')
else:
    app.config.from_pyfile('flaskapp.cfg')
if 'LVFS_CUSTOM_SETTINGS' in os.environ:
    app.config.from_envvar('LVFS_CUSTOM_SETTINGS')

db = Database()
db.init_app(app)

@app.cli.command('initdb')
def initdb_command():
    db.init_db()

@app.cli.command('dropdb')
def dropdb_command():
    db.drop_db()

@app.cli.command('modifydb')
def modifydb_command():
    db.modify_db()

def flash_save_eventlog(unused_sender, message, category, **unused_extra):
    is_important = False
    if category in ['danger', 'warning']:
        is_important = True
    _event_log(message, is_important)

message_flashed.connect(flash_save_eventlog, app)

lm = LoginManager()
lm.init_app(app)

ploader = Pluginloader('plugins')

@app.teardown_appcontext
def shutdown_session(unused_exception=None):
    db.session.remove()

@lm.user_loader
def load_user(user_id):
    from .models import User
    g.user = db.session.query(User).filter(User.username == user_id).first()
    return g.user

@app.errorhandler(404)
def error_page_not_found(msg=None):
    """ Error handler: File not found """

    # the world is a horrible place
    if request.path in ['/wp-login.php',
                        '/a2billing/common/javascript/misc.js']:
        return Response(response='bad karma', status=404, mimetype="text/plain")

    # flash, recording to the eventlog too
    flash(str(msg))
    return render_template('error.html'), 404

from app import views
from app import views_user
from app import views_group
from app import views_device
from app import views_firmware
from app import views_vendor
from app import views_component
from app import views_telemetry
from app import views_report
from app import views_metadata
from app import views_settings
from app import views_analytics
from app import views_upload
from app import views_issue
from app import views_search
