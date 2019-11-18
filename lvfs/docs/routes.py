#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2015-2018 Richard Hughes <richard@hughsie.com>
#
# SPDX-License-Identifier: GPL-2.0+
#
# pylint: disable=wrong-import-position,singleton-comparison

from flask import Blueprint, flash, url_for, redirect, render_template

from lvfs import app, db

from lvfs.models import Firmware, Component, Protocol, Category, Agreement, Verfmt, Vendor

bp_docs = Blueprint('docs', __name__, template_folder='templates')

@app.route('/developers') # deprecated
@bp_docs.route('/developers')
def route_developers():
    return render_template('docs-developers.html')

@app.route('/privacy') # deprecated
@bp_docs.route('/privacy')
def route_privacy():
    return render_template('docs-privacy.html')

@app.route('/users') # deprecated
@bp_docs.route('/users')
def route_users():
    return render_template('docs-users.html')

@bp_docs.route('/lvfs/news')
def route_news():
    return render_template('docs-news.html', category='home')

@app.route('/vendors')
@bp_docs.route('/vendors')
def route_vendors():
    return render_template('docs-vendors.html')

@app.route('/metainfo') # deprecated
@bp_docs.route('/metainfo')
@bp_docs.route('/metainfo/<page>')
def route_metainfo(page='intro'):
    if page not in ['intro', 'style', 'restrict', 'protocol', 'version', 'urls', 'category']:
        flash('No metainfo page name {}'.format(page), 'danger')
        return redirect(url_for('docs.route_metainfo'))
    protocols = db.session.query(Protocol).order_by(Protocol.protocol_id.asc()).all()
    categories = db.session.query(Category).order_by(Category.category_id.asc()).all()
    verfmts = db.session.query(Verfmt).order_by(Verfmt.verfmt_id.asc()).all()
    return render_template('docs-metainfo-%s.html' % page,
                           category='documentation',
                           protocols=protocols,
                           categories=categories,
                           verfmts=verfmts,
                           page=page)

@bp_docs.route('/composite')
def route_composite():
    return render_template('docs-composite.html', category='documentation')

@bp_docs.route('/archive')
def route_archive():
    return render_template('docs-archive.html', category='documentation')

@bp_docs.route('/telemetry')
def route_telemetry():
    return render_template('docs-telemetry.html', category='documentation')

@bp_docs.route('/agreement')
def route_agreement():
    agreement = db.session.query(Agreement).\
                    order_by(Agreement.version.desc()).first()
    return render_template('docs-agreement.html',
                           category='documentation',
                           agreement=agreement)

@bp_docs.route('/introduction')
def route_introduction():
    return render_template('docs-introduction.html',
                           firmware_cnt=db.session.query(Firmware).count(),
                           devices_cnt=db.session.query(Component.appstream_id).distinct().count())

@bp_docs.route('/consulting')
def route_consulting():
    vendors = db.session.query(Vendor).\
                    filter(Vendor.consulting_text != None).\
                    order_by(Vendor.display_name.desc()).all()
    return render_template('docs-consulting.html',
                           category='documentation',
                           vendors=vendors)

@bp_docs.route('/affiliates')
def route_affiliates():
    return render_template('docs-affiliates.html', category='documentation')
