#!/usr/bin/python2
# -*- coding: utf-8 -*-
#
# Copyright (C) 2017-2018 Richard Hughes <richard@hughsie.com>
# Licensed under the GNU General Public License Version 2

import datetime

from flask import render_template, g
from flask_login import login_required

from app import app, db

from .models import UserCapability, DownloadKind, Analytic, Client, Report
from .models import _get_datestr_from_datetime
from .util import _error_permission_denied
from .util import _get_chart_labels_months, _get_chart_labels_days

@app.route('/lvfs/analytics')
@app.route('/lvfs/analytics/month')
@login_required
def analytics_month():
    """ A analytics screen to show information about users """

    # security check
    if not g.user.check_capability(UserCapability.Admin):
        return _error_permission_denied('Unable to view analytics')

    # this is somewhat klunky
    data = []
    now = datetime.date.today()
    for _ in range(30):
        datestr = _get_datestr_from_datetime(now)
        analytic = db.session.query(Analytic).\
                        filter(Analytic.kind == DownloadKind.FIRMWARE).\
                        filter(Analytic.datestr == datestr).\
                        first()
        if analytic:
            data.append(int(analytic.cnt))
        else:
            data.append(0)

        # back one day
        now -= datetime.timedelta(days=1)

    return render_template('analytics-month.html',
                           labels_days=_get_chart_labels_days()[::-1],
                           data_days=data[::-1])

@app.route('/lvfs/analytics/year')
@login_required
def analytics_year():
    """ A analytics screen to show information about users """

    # security check
    if not g.user.check_capability(UserCapability.Admin):
        return _error_permission_denied('Unable to view analytics')

    # this is somewhat klunky
    data = []
    now = datetime.date.today()
    for _ in range(12):
        datestrold = _get_datestr_from_datetime(now)
        now -= datetime.timedelta(days=30)
        datestrnew = _get_datestr_from_datetime(now)
        analytics = db.session.query(Analytic).\
                        filter(Analytic.kind == DownloadKind.FIRMWARE).\
                        filter(Analytic.datestr < datestrold).\
                        filter(Analytic.datestr > datestrnew).\
                        all()

        # sum up all the totals for each day in that month
        cnt = 0
        for analytic in analytics:
            cnt += analytic.cnt
        data.append(int(cnt))

    return render_template('analytics-year.html',
                           labels_months=_get_chart_labels_months()[::-1],
                           data_months=data[::-1])

@app.route('/lvfs/analytics/user_agent')
@login_required
def analytics_user_agents():
    """ A analytics screen to show information about users """

    # security check
    if not g.user.check_capability(UserCapability.Admin):
        return _error_permission_denied('Unable to view analytics')

    # dedupe
    dedupe = {}
    for user_agent in db.session.query(Client).\
                            with_entities(Client.user_agent).\
                            filter(Client.user_agent != None).all():
        chunk = user_agent[0].split(' ')[0]
        if not chunk in dedupe:
            dedupe[chunk] = 1
            continue
        dedupe[chunk] += 1

    # get top user_agent strings
    labels = []
    data = []
    for key, value in sorted(dedupe.iteritems(), key=lambda (k, v): (v, k), reverse=True):
        labels.append(str(key.replace('/', ' ')))
        data.append(value)
        if len(data) >= 7:
            break

    return render_template('analytics-user-agent.html',
                           labels_user_agent=labels,
                           data_user_agent=data)

@app.route('/lvfs/analytics/clients')
@login_required
def analytics_clients():
    """ A analytics screen to show information about users """

    # security check
    if not g.user.check_capability(UserCapability.Admin):
        return _error_permission_denied('Unable to view analytics')
    clients = db.session.query(Client).limit(25).all()
    return render_template('analytics-clients.html', clients=clients)

@app.route('/lvfs/analytics/reports')
@login_required
def analytics_reports():
    """ A analytics screen to show information about users """

    # security check
    if not g.user.check_capability(UserCapability.Admin):
        return _error_permission_denied('Unable to view analytics')
    reports = db.session.query(Report).\
                    order_by(Report.timestamp.desc()).\
                    limit(25).all()
    return render_template('analytics-reports.html', reports=reports)
