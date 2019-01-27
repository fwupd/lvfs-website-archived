#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2018 Richard Hughes <richard@hughsie.com>
# Licensed under the GNU General Public License Version 2

from flask import render_template, request, url_for, redirect, flash, g
from flask_login import login_required

from app import app, db, ploader

from .models import Setting
from .util import _event_log, _error_permission_denied, _get_settings

@app.route('/lvfs/settings')
@app.route('/lvfs/settings/<plugin_id>')
@login_required
def settings_view(plugin_id='general'):
    """
    Allows the admin to change details about the LVFS instance
    """
    # security check
    if not g.user.check_acl('@admin'):
        return _error_permission_denied('Only admin is allowed to change settings')
    return render_template('settings.html',
                           settings=_get_settings(),
                           plugins=ploader.get_all(),
                           plugin_id=plugin_id)

@app.route('/lvfs/settings_create')
@login_required
def settings_create():

    # security check
    if not g.user.check_acl('@admin'):
        return _error_permission_denied('Only admin is allowed to change settings')

    # create all the plugin default keys
    settings = _get_settings()
    for plugin in ploader.get_all():
        for s in plugin.settings():
            if s.key not in settings:
                db.session.add(Setting(s.key, s.default))
    db.session.commit()
    return redirect(url_for('.settings_view'))

@app.route('/lvfs/settings/modify', methods=['GET', 'POST'])
@app.route('/lvfs/settings/modify/<plugin_id>', methods=['GET', 'POST'])
@login_required
def settings_modify(plugin_id='general'):
    """ Change details about the instance """

    # only accept form data
    if request.method != 'POST':
        return redirect(url_for('.settings_view', plugin_id=plugin_id))

    # security check
    if not g.user.check_acl('@admin'):
        return _error_permission_denied('Unable to modify settings as non-admin')

    # save new values
    settings = _get_settings()
    for key in request.form:
        if settings[key] == request.form[key]:
            continue
        setting = db.session.query(Setting).filter(Setting.key == key).first()
        setting.value = request.form[key]
        _event_log('Changed server settings %s to %s' % (key, setting.value))
    db.session.commit()
    flash('Updated settings', 'info')
    return redirect(url_for('.settings_view', plugin_id=plugin_id), 302)
