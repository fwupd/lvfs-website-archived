#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2015-2018 Richard Hughes <richard@hughsie.com>
#
# SPDX-License-Identifier: GPL-2.0+
#
# pylint: disable=wrong-import-position,singleton-comparison

from flask import Blueprint, redirect, render_template

from lvfs import app, db

from lvfs.models import Protocol, Agreement, Verfmt, Vendor

bp_docs = Blueprint('docs', __name__, template_folder='templates')

@app.route('/developers') # deprecated
@bp_docs.route('/developers')
def route_developers():
    return render_template('docs-developers.html')

@app.route('/privacy') # deprecated
@bp_docs.route('/privacy')
def route_privacy():
    return redirect('https://lvfs.readthedocs.io/en/latest/privacy.html', code=302)

@app.route('/users') # deprecated
@bp_docs.route('/users')
def route_users():
    return render_template('docs-users.html')

@bp_docs.route('/lvfs/news')
def route_news():
    return redirect('https://lvfs.readthedocs.io/en/latest/news.html', code=302)

@app.route('/vendors')
@bp_docs.route('/vendors')
def route_vendors():
    return render_template('docs-vendors.html')

@bp_docs.route('/metainfo/version')
def route_metainfo_version():
    verfmts = db.session.query(Verfmt).order_by(Verfmt.verfmt_id.asc()).all()
    return render_template('docs-metainfo-version.html',
                           category='documentation',
                           verfmts=verfmts)

@bp_docs.route('/metainfo/protocol')
def route_metainfo_protocol():
    protocols = db.session.query(Protocol).order_by(Protocol.protocol_id.asc()).all()
    return render_template('docs-metainfo-protocol.html',
                           category='documentation',
                           protocols=protocols)

@app.route('/metainfo') # deprecated
@bp_docs.route('/composite')
@bp_docs.route('/metainfo')
@bp_docs.route('/metainfo/category')
@bp_docs.route('/metainfo/intro')
@bp_docs.route('/metainfo/restrict')
@bp_docs.route('/metainfo/style')
@bp_docs.route('/metainfo/urls')
def route_metainfo():
    return redirect('https://lvfs.readthedocs.io/en/latest/metainfo.html', code=302)

@bp_docs.route('/archive')
@bp_docs.route('/affiliates')
def route_archive():
    return redirect('https://lvfs.readthedocs.io/en/latest/upload.html', code=302)

@bp_docs.route('/telemetry')
def route_telemetry():
    return redirect('https://lvfs.readthedocs.io/en/latest/telemetry.html', code=302)

@bp_docs.route('/introduction')
def route_introduction():
    return redirect('https://lvfs.readthedocs.io/en/latest/intro.html', code=302)

@bp_docs.route('/agreement')
def route_agreement():
    agreement = db.session.query(Agreement).\
                    order_by(Agreement.version.desc()).first()
    return render_template('docs-agreement.html',
                           category='documentation',
                           agreement=agreement)

@bp_docs.route('/consulting')
def route_consulting():
    vendors = db.session.query(Vendor).\
                    filter(Vendor.consulting_text != None).\
                    order_by(Vendor.display_name.desc()).all()
    return render_template('docs-consulting.html',
                           category='documentation',
                           vendors=vendors)

@bp_docs.route('/consulting/info')
def route_consulting_info():
    return render_template('docs-consulting-info.html',
                           category='documentation')
