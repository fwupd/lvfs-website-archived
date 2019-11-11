#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2018 Richard Hughes <richard@hughsie.com>
#
# SPDX-License-Identifier: GPL-2.0+

from collections import defaultdict

from flask import render_template, request, url_for, redirect, flash
from flask_login import login_required

from lvfs import app, db, ploader

from .models import Setting, Test, Firmware
from .util import _event_log, _get_settings
from .util import admin_login_required

def _convert_tests_for_plugin(plugin):
    tests_by_type = defaultdict(list)
    for test in db.session.query(Test).join(Firmware).\
                         filter(Test.plugin_id == plugin.id). \
                         order_by(Test.scheduled_ts.desc()):
        if len(tests_by_type['recent']) < 20:
            tests_by_type['recent'].append(test)
        if test.is_pending:
            tests_by_type['pending'].append(test)
        elif test.is_running:
            tests_by_type['running'].append(test)
        elif test.waived_ts:
            tests_by_type['waived'].append(test)
        elif test.success:
            tests_by_type['success'].append(test)
        else:
            tests_by_type['failed'].append(test)
    return tests_by_type

@app.route('/lvfs/settings')
@app.route('/lvfs/settings/<plugin_id>')
@login_required
@admin_login_required
def route_settings_view(plugin_id='general'):
    """
    Allows the admin to change details about the LVFS instance
    """
    plugin = ploader.get_by_id(plugin_id)
    if not plugin:
        flash('No plugin {}'.format(plugin_id), 'danger')
        return redirect(url_for('.route_settings_view'))
    tests_by_type = _convert_tests_for_plugin(plugin)
    return render_template('settings.html',
                           category='settings',
                           settings=_get_settings(),
                           plugin=plugin,
                           tests_by_type=tests_by_type)

@app.route('/lvfs/settings/<plugin_id>/tests/<kind>')
@login_required
@admin_login_required
def route_settings_tests(plugin_id, kind):
    """
    Allows the admin to change details about the LVFS instance
    """
    plugin = ploader.get_by_id(plugin_id)
    if not plugin:
        flash('No plugin {}'.format(plugin_id), 'danger')
        return redirect(url_for('.route_settings_view'))
    tests_by_type = _convert_tests_for_plugin(plugin)
    return render_template('settings-tests.html',
                           category='settings',
                           tests=tests_by_type[kind][:50],
                           tests_by_type=tests_by_type,
                           plugin=plugin)

@app.route('/lvfs/settings/create')
@login_required
@admin_login_required
def route_settings_create():

    # create all the plugin default keys
    settings = _get_settings()
    for plugin in ploader.get_all():
        for s in plugin.settings():
            if s.key not in settings:
                db.session.add(Setting(s.key, s.default))
    db.session.commit()
    return redirect(url_for('.route_settings_view'))

def _textarea_string_to_text(value_unsafe):
    values = []
    for value in value_unsafe.replace('\r', '').split('\n'):
        value = value.strip()
        if value:
            values.append(value)
    return ','.join(values)

@app.route('/lvfs/settings/modify', methods=['GET', 'POST'])
@app.route('/lvfs/settings/modify/<plugin_id>', methods=['GET', 'POST'])
@login_required
@admin_login_required
def route_settings_modify(plugin_id='general'):
    """ Change details about the instance """

    # only accept form data
    if request.method != 'POST':
        return redirect(url_for('.route_settings_view', plugin_id=plugin_id))

    # save new values
    settings = _get_settings()
    for key in request.form:
        if key == 'csrf_token':
            continue
        if settings[key] == request.form[key]:
            continue
        setting = db.session.query(Setting).filter(Setting.key == key).first()
        setting.value = _textarea_string_to_text(request.form[key])
        _event_log('Changed server settings %s to %s' % (key, setting.value))
    db.session.commit()
    flash('Updated settings', 'info')
    return redirect(url_for('.route_settings_view', plugin_id=plugin_id), 302)
