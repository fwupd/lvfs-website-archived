#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2018 Richard Hughes <richard@hughsie.com>
#
# SPDX-License-Identifier: GPL-2.0+

from flask import Blueprint, request, url_for, redirect, flash, g, render_template
from flask_login import login_required

from lvfs import db

from lvfs.models import Issue, Condition, Report, ReportAttribute
from lvfs.util import _error_internal

bp_issues = Blueprint('issues', __name__, template_folder='templates')

@bp_issues.route('/')
@login_required
def route_list():

    # security check
    if not g.user.check_acl('@view-issues'):
        flash('Permission denied: Unable to view issues', 'danger')
        return redirect(url_for('issues.route_list'))

    # only show issues with the correct group_id
    issues = []
    for issue in db.session.query(Issue).order_by(Issue.priority.desc()):
        if issue.check_acl('@view'):
            issues.append(issue)
    return render_template('issue-list.html',
                           category='firmware',
                           issues=issues)

@bp_issues.route('/create', methods=['POST'])
@login_required
def route_create():

    # security check
    if not Issue().check_acl('@create'):
        flash('Permission denied: Unable to add issue', 'danger')
        return redirect(url_for('issues.route_list'))

    # ensure has enough data
    for key in ['url']:
        if key not in request.form:
            return _error_internal('No %s form data found!', key)

    # already exists
    if db.session.query(Issue).\
            filter(Issue.url == request.form['url']).first():
        flash('Failed to add issue: The URL already exists', 'info')
        return redirect(url_for('issues.route_list'))

    # add issue
    issue = Issue(url=request.form['url'], vendor_id=g.user.vendor_id)
    db.session.add(issue)
    db.session.commit()
    flash('Added issue', 'info')
    return redirect(url_for('issues.route_show', issue_id=issue.issue_id))

@bp_issues.route('/<issue_id>/condition/create', methods=['POST'])
@login_required
def route_condition_create(issue_id):

    # ensure has enough data
    for key in ['key', 'value', 'compare']:
        if key not in request.form:
            return _error_internal('No %s form data found!' % key)

    # security check
    issue = db.session.query(Issue).\
                filter(Issue.issue_id == issue_id).first()
    if not issue:
        flash('No issue found', 'info')
        return redirect(url_for('issues.route_conditions', issue_id=issue_id))
    if not issue.check_acl('@modify'):
        flash('Permission denied: Unable to add condition to issue', 'danger')
        return redirect(url_for('issues.route_list'))

    # already exists
    if db.session.query(Condition).\
            filter(Condition.key == request.form['key']).\
            filter(Condition.issue_id == issue_id).first():
        flash('Failed to add condition to issue: Key %s already exists' % request.form['key'], 'info')
        return redirect(url_for('issues.route_conditions', issue_id=issue_id))

    # add condition
    db.session.add(Condition(issue_id=issue_id,
                             key=request.form['key'],
                             value=request.form['value'],
                             compare=request.form['compare']))
    db.session.commit()
    flash('Added condition', 'info')
    return redirect(url_for('issues.route_conditions', issue_id=issue_id))

@bp_issues.route('/<issue_id>/condition/<int:condition_id>/delete', methods=['POST'])
@login_required
def route_condition_delete(issue_id, condition_id):

    # disable issue
    issue = db.session.query(Issue).\
                filter(Issue.issue_id == issue_id).first()
    if not issue:
        flash('No issue found', 'info')
        return redirect(url_for('issues.route_list'))

    # security check
    if not issue.check_acl('@modify'):
        flash('Permission denied: Unable to delete condition from issue', 'danger')
        return redirect(url_for('issues.route_list'))

    # get issue
    condition = db.session.query(Condition).\
            filter(Condition.issue_id == issue_id).\
            filter(Condition.condition_id == condition_id).first()
    if not condition:
        flash('No condition found', 'info')
        return redirect(url_for('issues.route_list'))

    # delete
    issue.enabled = False
    db.session.delete(condition)
    db.session.commit()
    flash('Deleted condition, and disabled issue for safety', 'info')
    return redirect(url_for('issues.route_conditions', issue_id=condition.issue_id))

@bp_issues.route('/<int:issue_id>/delete', methods=['POST'])
@login_required
def route_delete(issue_id):

    # get issue
    issue = db.session.query(Issue).\
            filter(Issue.issue_id == issue_id).first()
    if not issue:
        flash('No issue found', 'info')
        return redirect(url_for('issues.route_list'))

    # security check
    if not issue.check_acl('@modify'):
        flash('Permission denied: Unable to delete report', 'danger')
        return redirect(url_for('issues.route_list'))

    # delete
    for condition in issue.conditions:
        db.session.delete(condition)
    db.session.delete(issue)
    db.session.commit()
    flash('Deleted issue', 'info')
    return redirect(url_for('issues.route_list'))


def _create_query_for_conditions(issue):

    # use a set of subqueries for speed
    subqs = []
    for cond in issue.conditions:
        if cond.compare == 'eq':
            subqs.append(db.session.query(ReportAttribute.report_id)\
                                   .filter(ReportAttribute.key == cond.key,
                                           ReportAttribute.value == cond.value).subquery())
        elif cond.compare == 'lt':
            subqs.append(db.session.query(ReportAttribute.report_id)\
                                   .filter(ReportAttribute.key == cond.key,
                                           ReportAttribute.value < cond.value).subquery())
        elif cond.compare == 'le':
            subqs.append(db.session.query(ReportAttribute.report_id)\
                                   .filter(ReportAttribute.key == cond.key,
                                           ReportAttribute.value <= cond.value).subquery())
        elif cond.compare == 'gt':
            subqs.append(db.session.query(ReportAttribute.report_id)\
                                   .filter(ReportAttribute.key == cond.key,
                                           ReportAttribute.value > cond.value).subquery())
        elif cond.compare == 'ge':
            subqs.append(db.session.query(ReportAttribute.report_id)\
                                   .filter(ReportAttribute.key == cond.key,
                                           ReportAttribute.value >= cond.value).subquery())
        elif cond.compare == 'glob':
            value = cond.value.replace('*', '%')
            subqs.append(db.session.query(ReportAttribute.report_id)\
                                   .filter(ReportAttribute.key == cond.key,
                                           ReportAttribute.value.like(value)).subquery())
        elif cond.compare == 'regex':
            subqs.append(db.session.query(ReportAttribute.report_id)\
                                   .filter(ReportAttribute.key == cond.key,
                                           ReportAttribute.value.op('~')(cond.value)).subquery())
    stmt = db.session.query(Report)
    for subq in subqs:
        stmt = stmt.join(subq, Report.report_id == subq.c.report_id)
    return stmt

def _issue_fix_report_failures(issue):

    # process each report
    change_cnt = 0
    stmt = _create_query_for_conditions(issue)
    for report in stmt.filter(Report.issue_id == 0):

        # check we can apply changes to this firmware
        if not report.fw.check_acl('@delete'):
            continue

        # fix issue ID so we look better in the analytics pages
        report.issue_id = issue.issue_id
        change_cnt += 1

    # save changes
    if change_cnt:
        db.session.commit()

    # return number of changes
    return change_cnt

@bp_issues.route('/<int:issue_id>/modify', methods=['POST'])
@login_required
def route_modify(issue_id):

    # find issue
    issue = db.session.query(Issue).\
                filter(Issue.issue_id == issue_id).first()
    if not issue:
        flash('No issue found', 'info')
        return redirect(url_for('issues.route_list'))

    # security check
    if not issue.check_acl('@modify'):
        flash('Permission denied: Unable to modify issue', 'danger')
        return redirect(url_for('issues.route_list'))

    # issue cannot be enabled if it has no conditions
    if 'enabled' in request.form and not issue.conditions:
        flash('Issue can not be enabled without conditions', 'warning')
        return redirect(url_for('issues.route_show', issue_id=issue_id))

    # modify issue
    issue.enabled = bool('enabled' in request.form)
    for key in ['url', 'name', 'description']:
        if key in request.form:
            setattr(issue, key, request.form[key])
    db.session.commit()

    # if we enabled a new issue try to tag failures as known-failures
    cnt_fixed = 0
    if issue.enabled:
        cnt_fixed = _issue_fix_report_failures(issue)

    # success
    if cnt_fixed > 0:
        flash('Modified issue (fixing %i reports)' % cnt_fixed, 'info')
    else:
        flash('Modified issue', 'info')
    return redirect(url_for('issues.route_show', issue_id=issue_id))

@bp_issues.route('/<int:issue_id>/details')
@login_required
def route_show(issue_id):

    # find issue
    issue = db.session.query(Issue).\
            filter(Issue.issue_id == issue_id).first()
    if not issue:
        flash('No issue found', 'info')
        return redirect(url_for('issues.route_list'))

    # security check
    if not issue.check_acl('@view'):
        flash('Permission denied: Unable to view issue details', 'danger')
        return redirect(url_for('issues.route_list'))

    # show details
    return render_template('issue-details.html',
                           category='firmware',
                           issue=issue)

@bp_issues.route('/<int:issue_id>/priority/<op>')
@login_required
def route_priority(issue_id, op):

    # find issue
    issue = db.session.query(Issue).\
            filter(Issue.issue_id == issue_id).first()
    if not issue:
        flash('No issue found', 'info')
        return redirect(url_for('issues.route_list'))

    # security check
    if not issue.check_acl('@modify'):
        flash('Permission denied: Unable to change issue priority', 'danger')
        return redirect(url_for('issues.route_list'))

    # change integer priority
    if op == 'up':
        issue.priority += 1
    elif op == 'down':
        issue.priority -= 1
    else:
        return _error_internal('Operation %s invalid!', op)
    db.session.commit()

    # show details
    return redirect(url_for('issues.route_list'))

@bp_issues.route('/<int:issue_id>/reports')
@login_required
def route_reports(issue_id):

    # find issue
    issue = db.session.query(Issue).\
            filter(Issue.issue_id == issue_id).first()
    if not issue:
        flash('No issue found', 'info')
        return redirect(url_for('issues.route_list'))

    # security check
    if not issue.check_acl('@view'):
        flash('Permission denied: Unable to view issue reports', 'danger')
        return redirect(url_for('issues.route_list'))

    # check firmware details are available to this user
    reports = []
    reports_hidden = []
    stmt = _create_query_for_conditions(issue)
    reports_unfiltered = stmt.order_by(Report.timestamp.desc()).limit(10).all()
    for report in reports_unfiltered:
        if not report.fw.check_acl('@view'):
            reports_hidden.append(report)
            continue
        reports.append(report)

    # show reports
    return render_template('issue-reports.html',
                           category='firmware',
                           issue=issue,
                           reports=reports,
                           reports_hidden=reports_hidden,
                           reports_cnt=len(reports_unfiltered))

@bp_issues.route('/<int:issue_id>/conditions')
@login_required
def route_conditions(issue_id):

    # find issue
    issue = db.session.query(Issue).\
            filter(Issue.issue_id == issue_id).first()
    if not issue:
        flash('No issue found', 'info')
        return redirect(url_for('issues.route_list'))

    # security check
    if not issue.check_acl('@view'):
        flash('Permission denied: Unable to view issue conditions', 'danger')
        return redirect(url_for('issues.route_list'))

    # show details
    return render_template('issue-conditions.html',
                           category='firmware',
                           issue=issue)
