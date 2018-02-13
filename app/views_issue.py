#!/usr/bin/python2
# -*- coding: utf-8 -*-
#
# Copyright (C) 2018 Richard Hughes <richard@hughsie.com>
# Licensed under the GNU General Public License Version 2

from flask import request, url_for, redirect, flash, g, render_template
from flask_login import login_required

from app import app, db

from .models import Issue, Condition, Report, Firmware, UserCapability
from .util import _error_internal, _error_permission_denied

@app.route('/lvfs/issue/all')
@login_required
def issue_all():

    # permission check
    if not g.user.check_capability(UserCapability.QA):
        return _error_permission_denied('Unable to view issues')

    # only show issues with the correct group_id
    issues = []
    for issue in db.session.query(Issue).all():
        if g.user.check_for_issue(issue, readonly=True):
            issues.append(issue)
    return render_template('issue-list.html', issues=issues)

@app.route('/lvfs/issue/add', methods=['POST'])
@login_required
def issue_add():

    # permission check
    if not g.user.check_capability(UserCapability.QA):
        return _error_permission_denied('Unable to add report')

    # ensure has enough data
    for key in ['url']:
        if key not in request.form:
            return _error_internal('No %s form data found!', key)

    # already exists
    if db.session.query(Issue).\
            filter(Issue.url == request.form['url']).first():
        flash('An issue already exists with that url', 'info')
        return redirect(url_for('.issue_all'))

    # add issue
    issue = Issue(url=request.form['url'], group_id=g.user.group_id)
    db.session.add(issue)
    db.session.commit()
    flash('Added issue', 'info')
    return redirect(url_for('.issue_details', issue_id=issue.issue_id))

@app.route('/lvfs/issue/<issue_id>/condition/add', methods=['POST'])
@login_required
def issue_condition_add(issue_id):

    # ensure has enough data
    for key in ['key', 'value', 'compare']:
        if key not in request.form:
            return _error_internal('No %s form data found!' % key)

    # permission check
    issue = db.session.query(Issue).\
                filter(Issue.issue_id == issue_id).first()
    if not issue:
        flash('No issue found', 'info')
        return redirect(url_for('.issue_conditions', issue_id=issue_id))
    if not g.user.check_for_issue(issue):
        return _error_permission_denied('Unable to add condition to report')

    # already exists
    if db.session.query(Condition).\
            filter(Condition.key == request.form['key']).\
            filter(Condition.issue_id == issue_id).first():
        flash('A condition already exists for this issue with key %s' % request.form['key'], 'info')
        return redirect(url_for('.issue_conditions', issue_id=issue_id))

    # add condition
    db.session.add(Condition(issue_id,
                             request.form['key'],
                             request.form['value'],
                             request.form['compare']))
    db.session.commit()
    flash('Added condition', 'info')
    return redirect(url_for('.issue_conditions', issue_id=issue_id))

@app.route('/lvfs/issue/<issue_id>/condition/<int:condition_id>/delete')
@login_required
def issue_condition_delete(issue_id, condition_id):

    # disable issue
    issue = db.session.query(Issue).\
                filter(Issue.issue_id == issue_id).first()
    if not issue:
        flash('No issue found', 'info')
        return redirect(url_for('.issue_all'))

    # permission check
    if not g.user.check_for_issue(issue):
        return _error_permission_denied('Unable to delete condition from report')

    # get issue
    condition = db.session.query(Condition).\
            filter(Condition.issue_id == issue_id).\
            filter(Condition.condition_id == condition_id).first()
    if not condition:
        flash('No condition found', 'info')
        return redirect(url_for('.issue_all'))

    # delete
    issue.enabled = False
    db.session.delete(condition)
    db.session.commit()
    flash('Deleted condition, and disabled issue for safety', 'info')
    return redirect(url_for('.issue_conditions', issue_id=condition.issue_id))

@app.route('/lvfs/issue/<int:issue_id>/delete')
@login_required
def issue_delete(issue_id):

    # get issue
    issue = db.session.query(Issue).\
            filter(Issue.issue_id == issue_id).first()
    if not issue:
        flash('No issue found', 'info')
        return redirect(url_for('.issue_all'))

    # permission check
    if not g.user.check_for_issue(issue):
        return _error_permission_denied('Unable to delete report')

    # delete
    db.session.delete(issue)
    db.session.commit()
    flash('Deleted issue', 'info')
    return redirect(url_for('.issue_all'))

@app.route('/lvfs/issue/<int:issue_id>/modify', methods=['POST'])
@login_required
def issue_modify(issue_id):

    # find issue
    issue = db.session.query(Issue).\
                filter(Issue.issue_id == issue_id).first()
    if not issue:
        flash('No issue found', 'info')
        return redirect(url_for('.issue_all'))

    # permission check
    if not g.user.check_for_issue(issue):
        return _error_permission_denied('Unable to modify report')

    # issue cannot be enabled if it has no conditions
    if 'enabled' in request.form and not issue.conditions:
        flash('Issue can not be enabled without conditions', 'warning')
        return redirect(url_for('.issue_details', issue_id=issue_id))

    # modify issue
    issue.enabled = True if 'enabled' in request.form else False
    for key in ['url', 'name', 'description', 'group_id']:
        if key in request.form:
            setattr(issue, key, request.form[key])
    db.session.commit()

    # success
    flash('Modified issue', 'info')
    return redirect(url_for('.issue_details', issue_id=issue_id))

@app.route('/lvfs/issue/<int:issue_id>/details')
@login_required
def issue_details(issue_id):

    # find issue
    issue = db.session.query(Issue).\
            filter(Issue.issue_id == issue_id).first()
    if not issue:
        flash('No issue found', 'info')
        return redirect(url_for('.issue_all'))

    # permission check
    if not g.user.check_for_issue(issue, readonly=True):
        return _error_permission_denied('Unable to view issue details')

    # show details
    return render_template('issue-details.html', issue=issue)

@app.route('/lvfs/issue/<int:issue_id>/reports')
@login_required
def issue_reports(issue_id):

    # find issue
    issue = db.session.query(Issue).\
            filter(Issue.issue_id == issue_id).first()
    if not issue:
        flash('No issue found', 'info')
        return redirect(url_for('.issue_all'))

    # permission check
    if not g.user.check_for_issue(issue, readonly=True):
        return _error_permission_denied('Unable to view issue reports')

    # check firmware details are available to this user, and check if it matches
    reports = []
    reports_hidden = []
    reports_cnt = 0
    for report in db.session.query(Report).all():
        data = report.to_flat_dict()
        if not issue.matches(data):
            continue
        reports_cnt += 1

        # limit this to the latest 10 reports
        if reports_cnt < 10:
            fw = db.session.query(Firmware).\
                    filter(Firmware.firmware_id == report.firmware_id).first()
            if not g.user.check_for_firmware(fw, readonly=True):
                reports_hidden.append(report)
                continue
            reports.append(report)

    # show reports
    return render_template('issue-reports.html',
                           issue=issue,
                           reports=reports,
                           reports_hidden=reports_hidden,
                           reports_cnt=reports_cnt)

@app.route('/lvfs/issue/<int:issue_id>/conditions')
@login_required
def issue_conditions(issue_id):

    # find issue
    issue = db.session.query(Issue).\
            filter(Issue.issue_id == issue_id).first()
    if not issue:
        flash('No issue found', 'info')
        return redirect(url_for('.issue_all'))

    # permission check
    if not g.user.check_for_issue(issue, readonly=True):
        return _error_permission_denied('Unable to view issue conditions')

    # show details
    return render_template('issue-conditions.html', issue=issue)
