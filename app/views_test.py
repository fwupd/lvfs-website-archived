#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2019 Richard Hughes <richard@hughsie.com>
# Licensed under the GNU General Public License Version 2
#
# pylint: disable=singleton-comparison

from flask import url_for, redirect, flash, render_template
from flask_login import login_required
from sqlalchemy.orm import joinedload

from app import app, db, ploader

from .models import Test
from .util import admin_login_required
from .util import _error_internal, _error_permission_denied

@app.route('/lvfs/test')
@app.route('/lvfs/test/overview')
@login_required
@admin_login_required
def test_overview():

    # get all the test data
    tests = db.session.query(Test).\
                options(joinedload('attributes')). \
                order_by(Test.scheduled_ts.desc()).all()
    plugin_ids = {}
    for test in tests:
        if test.plugin_id not in plugin_ids:
            plugin_ids[test.plugin_id] = []
        plugin_ids[test.plugin_id].append(test)
    tests_pending = {}
    tests_running = {}
    tests_success = {}
    tests_failed = {}
    tests_waived = {}
    for plugin_id in plugin_ids:
        tests_pending[plugin_id] = []
        tests_running[plugin_id] = []
        tests_success[plugin_id] = []
        tests_failed[plugin_id] = []
        tests_waived[plugin_id] = []
        for test in plugin_ids[plugin_id]:
            if test.is_pending:
                tests_pending[plugin_id].append(test)
            elif test.is_running:
                tests_running[plugin_id].append(test)
            elif test.waived_ts:
                tests_waived[plugin_id].append(test)
            elif test.success:
                tests_success[plugin_id].append(test)
            else:
                tests_failed[plugin_id].append(test)

    # get the actual Plugin for the ID
    plugins = {}
    for plugin_id in plugin_ids:
        plugins[plugin_id] = ploader.get_by_id(plugin_id)

    return render_template('test-overview.html',
                           category='tests',
                           plugins=plugins,
                           plugin_ids=plugin_ids,
                           tests_pending=tests_pending,
                           tests_running=tests_running,
                           tests_success=tests_success,
                           tests_waived=tests_waived,
                           tests_failed=tests_failed)

@app.route('/lvfs/test/recent')
@login_required
@admin_login_required
def test_recent():
    tests = db.session.query(Test).\
                filter(Test.started_ts != None). \
                filter(Test.ended_ts != None). \
                options(joinedload('attributes')). \
                order_by(Test.ended_ts.desc()).limit(20).all()
    return render_template('test-list.html', category='tests', tests=tests)

@app.route('/lvfs/test/running')
@login_required
@admin_login_required
def test_running():
    tests = db.session.query(Test). \
                filter(Test.started_ts != None). \
                filter(Test.ended_ts == None). \
                options(joinedload('attributes')). \
                order_by(Test.scheduled_ts.desc()).all()
    return render_template('test-list.html', category='tests', tests=tests)

@app.route('/lvfs/test/pending')
@login_required
@admin_login_required
def test_pending():
    tests = db.session.query(Test). \
                filter(Test.started_ts == None). \
                options(joinedload('attributes')). \
                order_by(Test.scheduled_ts.desc()).all()
    return render_template('test-list.html', category='tests', tests=tests)

@app.route('/lvfs/test/failed')
@login_required
@admin_login_required
def test_failed():
    tests = db.session.query(Test).\
                filter(Test.ended_ts != None). \
                filter(Test.waived_ts == None). \
                options(joinedload('attributes')). \
                order_by(Test.scheduled_ts.desc()).all()
    tests_failed = []
    for test in tests:
        if not test.success:
            tests_failed.append(test)
    return render_template('test-list.html', category='tests', tests=tests_failed)

@app.route('/lvfs/test/waived')
@login_required
@admin_login_required
def test_waived():
    tests = db.session.query(Test).\
                filter(Test.ended_ts != None). \
                filter(Test.waived_ts != None). \
                options(joinedload('attributes')). \
                order_by(Test.scheduled_ts.desc()).all()
    return render_template('test-list.html', category='tests', tests=tests)

@app.route('/lvfs/test/retry/<int:test_id>')
@login_required
def test_retry(test_id):

    # get test
    test = db.session.query(Test).filter(Test.test_id == test_id).first()
    if not test:
        return _error_internal('No test matched!')

    # security check
    if not test.check_acl('@retry'):
        return _error_permission_denied('Unable to retry test')

    # remove child
    test.retry()
    db.session.commit()

    # log
    flash('Test %s will be re-run soon' % test.plugin_id, 'info')
    return redirect(url_for('.firmware_tests', firmware_id=test.fw.firmware_id))

@app.route('/lvfs/test/waive/<int:test_id>')
@login_required
def test_waive(test_id):

    # get test
    test = db.session.query(Test).filter(Test.test_id == test_id).first()
    if not test:
        return _error_internal('No test matched!')

    # security check
    if not test.waivable or not test.check_acl('@waive'):
        return _error_permission_denied('Unable to waive test')

    # remove chid
    test.waive()
    db.session.commit()

    # log
    flash('Test %s was waived' % test.plugin_id, 'info')
    return redirect(url_for('.firmware_tests', firmware_id=test.fw.firmware_id))

@app.route('/lvfs/test/retry/<plugin_id>')
@login_required
@admin_login_required
def test_retry_all(plugin_id):

    # get tests
    tests = db.session.query(Test).\
                filter(Test.started_ts != None). \
                filter(Test.ended_ts == None). \
                filter(Test.plugin_id == plugin_id).all()
    if not tests:
        flash('No tests matched', 'warning')
        return redirect(url_for('.test_overview'))
    for test in tests:
        test.retry()
    db.session.commit()

    # log
    flash('%i tests will be re-run soon' % len(tests), 'info')
    return redirect(url_for('.test_overview'))

@app.route('/lvfs/test/waive/<plugin_id>')
@login_required
@admin_login_required
def test_waive_all(plugin_id):

    # get tests
    tests = db.session.query(Test).\
                filter(Test.ended_ts != None). \
                filter(Test.plugin_id == plugin_id). \
                filter(Test.waivable).all()
    tests_failed = []
    for test in tests:
        if not test.success:
            tests_failed.append(test)
    if not tests_failed:
        flash('No tests could be waived', 'warning')
        return redirect(url_for('.test_overview'))
    for test in tests_failed:
        test.waive()
    db.session.commit()

    # log
    flash('%i tests have been waived' % len(tests_failed), 'info')
    return redirect(url_for('.test_overview'))

@app.route('/lvfs/test/delete/<plugin_id>')
@login_required
@admin_login_required
def test_delete_all(plugin_id):

    # get tests
    tests = db.session.query(Test).\
                filter(Test.plugin_id == plugin_id).all()
    if not tests:
        flash('No tests matched', 'warning')
        return redirect(url_for('.test_overview'))
    for test in tests:
        db.session.delete(test)
    db.session.commit()

    # log
    flash('%i tests have been deleted' % len(tests), 'info')
    return redirect(url_for('.test_overview'))
