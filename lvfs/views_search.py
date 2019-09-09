#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2018 Richard Hughes <richard@hughsie.com>
#
# SPDX-License-Identifier: GPL-2.0+

from flask import request, render_template, flash, redirect, url_for
from flask_login import login_required

from sqlalchemy import func

from lvfs import app, db

from .models import Guid, Keyword, Vendor, SearchEvent, Component, Firmware, Remote
from .models import _split_search_string
from .hash import _addr_hash
from .util import admin_login_required
from .util import _get_client_address

@app.route('/lvfs/search/<int:search_event_id>/delete')
@login_required
@admin_login_required
def search_delete(search_event_id):
    ev = db.session.query(SearchEvent).filter(SearchEvent.search_event_id == search_event_id).first()
    if not ev:
        flash('No search found!', 'danger')
        return redirect(url_for('.search'))
    db.session.delete(ev)
    db.session.commit()
    flash('Deleted search event', 'info')
    return redirect(url_for('.analytics_search_history'))

def _add_search_event(ev):
    if db.session.query(SearchEvent).\
                        filter(SearchEvent.value == ev.value).\
                        filter(SearchEvent.addr == ev.addr).first():
        return
    db.session.add(ev)
    db.session.commit()

@app.route('/lvfs/firmware/search', methods=['GET', 'POST'])
@app.route('/lvfs/firmware/search/<int:max_results>', methods=['GET', 'POST'])
@login_required
def search_fw(max_results=100):

    if 'value' not in request.args:
        flash('No search value!', 'danger')
        return redirect(url_for('.search'))
    keywords = _split_search_string(request.args['value'])
    if not keywords:
        keywords = request.args['value'].split(' ')

    # use keywords first
    fws = db.session.query(Firmware).join(Component).\
                           join(Keyword).\
                           filter(Keyword.value.in_(keywords)).\
                           group_by(Keyword.component_id).\
                           having(func.count() == len(keywords)).\
                           distinct().order_by(Firmware.timestamp.desc()).\
                           limit(max_results).all()

    # try GUIDs
    if not fws:
        fws = db.session.query(Firmware).join(Component).\
                               join(Guid).\
                               filter(Guid.value.in_(keywords)).\
                               group_by(Guid.component_id).\
                               having(func.count() == len(keywords)).\
                               distinct().order_by(Firmware.timestamp.desc()).\
                               limit(max_results).all()

    # try version numbers
    if not fws:
        fws = db.session.query(Firmware).join(Component).\
                               filter(Component.version.in_(keywords)).\
                               group_by(Component.component_id).\
                               having(func.count() == len(keywords)).\
                               distinct().order_by(Firmware.timestamp.desc()).\
                               limit(max_results).all()

    # try appstream ID
    if not fws:
        fws = db.session.query(Firmware).join(Component).\
                               filter(Component.appstream_id.startswith(keywords[0])).\
                               group_by(Component.component_id).\
                               distinct().order_by(Firmware.timestamp.desc()).\
                               limit(max_results).all()

    # filter by ACL
    fws_safe = []
    for fw in fws:
        if fw.check_acl('@view'):
            fws_safe.append(fw)

    return render_template('firmware-search.html',
                           category='firmware',
                           state='search',
                           remote=None,
                           fws=fws_safe)

@app.route('/lvfs/search', methods=['GET', 'POST'])
@app.route('/lvfs/search/<int:max_results>', methods=['POST'])
def search(max_results=150):

    # no search results
    if 'value' not in request.args:
        return render_template('search.html',
                               mds=None,
                               search_size=-1,
                               keywords_good=[],
                               keywords_bad=[])

    # components that match
    keywords = _split_search_string(request.args['value'])
    ids = db.session.query(Keyword.component_id).\
                           filter(Keyword.value.in_(keywords)).\
                           group_by(Keyword.component_id).\
                           having(func.count() == len(keywords)).\
                           subquery()
    mds = []
    appstream_ids = []
    for md in db.session.query(Component).join(ids).\
                    join(Firmware).join(Remote).filter(Remote.is_public).\
                    order_by(Component.version.desc()).\
                    limit(max_results*4):
        if md.appstream_id in appstream_ids:
            continue
        mds.append(md)
        appstream_ids.append(md.appstream_id)

    # get any vendor information as a fallback
    vendors = []
    if mds:
        search_method = 'AND'
        show_vendor_nag = False
        keywords_good = keywords
        keywords_bad = []
    else:
        search_method = 'OR'
        show_vendor_nag = True
        keywords_good = []
        keywords_bad = []
        for vendor in db.session.query(Vendor).\
                            filter(Vendor.visible_for_search):
            for kw in keywords:
                if vendor.keywords:
                    if kw in vendor.keywords:
                        vendors.append(vendor)
                        keywords_good.append(kw)
                        break
                if vendor.display_name:
                    if kw in _split_search_string(vendor.display_name):
                        vendors.append(vendor)
                        keywords_good.append(kw)
                        break
        for kw in keywords:
            if not kw in keywords_good:
                keywords_bad.append(kw)

    # this seems like we're over-logging but I'd like to see how people are
    # searching so we can tweak the algorithm used
    _add_search_event(SearchEvent(value=request.args['value'],
                                  addr=_addr_hash(_get_client_address()),
                                  count=len(mds) + len(vendors),
                                  method=search_method))

    return render_template('search.html',
                           show_vendor_nag=show_vendor_nag,
                           mds=mds[:max_results],
                           search_size=len(mds),
                           vendors=vendors,
                           keywords_good=keywords_good,
                           keywords_bad=keywords_bad)
