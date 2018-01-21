#!/usr/bin/python2
# -*- coding: utf-8 -*-
#
# Copyright (C) 2015-2017 Richard Hughes <richard@hughsie.com>
# Licensed under the GNU General Public License Version 2

import os

from flask import Flask, flash, render_template, g
from flask.ext.login import LoginManager
from werkzeug.local import LocalProxy

from .db import Database
from .response import SecureResponse
from .pluginloader import Pluginloader

app = Flask(__name__)
app.response_class = SecureResponse
if os.path.exists('app/custom.cfg'):
    app.config.from_pyfile('custom.cfg')
else:
    app.config.from_pyfile('flaskapp.cfg')

lm = LoginManager()
lm.init_app(app)

ploader = Pluginloader('plugins')

# only load once per app context
def get_db():
    if not hasattr(g, 'db'):
        g.db = Database(app)
        g.db.verify()
    return g.db
db = LocalProxy(get_db)

@app.teardown_appcontext
def close_db(error):
    """Closes the database again at the end of the request."""
    if hasattr(g, 'db'):
        g.db.close()

@lm.user_loader
def load_user(user_id):
    user = db.users.get_item(user_id)
    return user

@app.errorhandler(404)
def error_page_not_found(msg=None):
    """ Error handler: File not found """
    flash(msg)
    return render_template('error.html'), 404

from app import views
from app import views_user
from app import views_group
from app import views_device
from app import views_firmware
from app import views_vendor
