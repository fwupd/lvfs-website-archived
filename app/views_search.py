#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2018 Richard Hughes <richard@hughsie.com>
# Licensed under the GNU General Public License Version 2

from flask import request, render_template, flash, redirect, url_for, g
from flask_login import login_required

from app import app, db

from .models import Guid, Keyword, Vendor, SearchEvent, _split_search_string
from .hash import _addr_hash
from .util import _get_client_address, _error_internal, _error_permission_denied

def _md_suitable_as_search_result(md):
    if not md:
        return False
    if not md.fw.remote.is_public:
        return False
    return True

def _order_by_summed_md_priority(md_priority):
    dedupe = []
    for md in md_priority:
        dedupe.append((md, md_priority[md]))
    filtered_mds = []
    component_ids = {}
    dedupe.sort(key=lambda k: k[0].component_id, reverse=True)
    dedupe.sort(key=lambda k: k[1], reverse=True)
    for md_compond in dedupe:
        md = md_compond[0]
        if md.appstream_id in component_ids:
            continue
        filtered_mds.append(md)
        component_ids[md.appstream_id] = md
    return filtered_mds

def _get_md_priority_for_kws(kws):
    md_priority = {}
    for kw in kws:
        md = kw.md
        if not _md_suitable_as_search_result(md):
            continue
        if md not in md_priority:
            md_priority[md] = kw.priority
        else:
            md_priority[md] += kw.priority
    return md_priority

@app.route('/lvfs/search/<int:search_event_id>/delete')
@login_required
def search_delete(search_event_id):
    # security check
    if not g.user.check_acl('@admin'):
        return _error_permission_denied('Unable to delete search')
    ev = db.session.query(SearchEvent).filter(SearchEvent.search_event_id == search_event_id).first()
    if not ev:
        return _error_internal('No search found!')
    db.session.delete(ev)
    db.session.commit()
    flash('Deleted search event', 'info')
    return redirect(url_for('.analytics_search_history'))

def _add_search_event(ev):
    if db.session.query(SearchEvent).\
                        filter(SearchEvent.value == ev.value).\
                        filter(SearchEvent.addr == ev.addr).all():
        return
    db.session.add(ev)
    db.session.commit()

@app.route('/lvfs/search', methods=['GET', 'POST'])
@app.route('/lvfs/search/<int:max_results>', methods=['POST'])
def search(max_results=19):

    # no search results
    if 'value' not in request.args:
        return render_template('search.html',
                               mds=None,
                               search_size=-1,
                               keywords_good=[],
                               keywords_bad=[])

    # show the user good and bad keyword matches
    keywords_good = []
    keywords_bad = []

    # search for each keyword in order
    kws = {}
    search_keywords = _split_search_string(request.args['value'])
    for keyword in search_keywords:
        kws[keyword] = db.session.query(Keyword).\
                            filter(Keyword.value == keyword).\
                            order_by(Keyword.keyword_id.desc()).all()

    # add GUIDs
    for keyword in search_keywords:
        guids = db.session.query(Guid).\
                        filter(Guid.value == keyword).\
                        order_by(Guid.guid_id.desc()).all()
        for guid in guids:
            kws[keyword] = [Keyword(keyword, priority=20, md=guid.md)]

    # get any vendor information
    vendors = []
    for vendor in db.session.query(Vendor).all():
        if not vendor.visible_for_search:
            continue
        vendor_keywords = []
        if vendor.display_name:
            vendor_keywords.extend(_split_search_string(vendor.display_name))
        if vendor.keywords:
            vendor_keywords.extend(_split_search_string(vendor.keywords))
        for keyword in vendor_keywords:
            if keyword in search_keywords:
                if vendor not in vendors:
                    vendors.append(vendor)
                if keyword not in keywords_good:
                    keywords_good.append(keyword)

    # do an AND search
    md_priority = {}
    mds_unique = []
    for keyword in search_keywords:
        md_priority_for_keyword = _get_md_priority_for_kws(kws[keyword])
        for md in md_priority_for_keyword:
            if not md in mds_unique:
                mds_unique.append(md)
        md_priority[keyword] = md_priority_for_keyword
    md_priority_in_all = {}
    for md in mds_unique:
        found_in_all = True
        priority_max = 0
        for keyword in search_keywords:
            if md not in md_priority[keyword]:
                found_in_all = False
                break
            if md_priority[keyword][md] > priority_max:
                priority_max = md_priority[keyword][md]
        if found_in_all:
            md_priority_in_all[md] = priority_max
    if len(md_priority_in_all) > 0:
        filtered_mds = _order_by_summed_md_priority(md_priority_in_all)
        for md in filtered_mds:
            if md.fw.vendor not in vendors:
                vendors.append(md.fw.vendor)
        # this seems like we're over-logging but I'd like to see how people are
        # searching for a few weeks so we can tweak the algorithm used
        _add_search_event(SearchEvent(value=request.args['value'],
                                      addr=_addr_hash(_get_client_address()),
                                      count=len(filtered_mds) + len(vendors),
                                      method='AND'))
        return render_template('search.html',
                               show_vendor_nag=False,
                               mds=filtered_mds[:max_results],
                               search_size=len(filtered_mds),
                               vendors=vendors,
                               keywords_good=search_keywords,
                               keywords_bad=[])

    # do an OR search
    md_priority = {}
    for keyword in search_keywords:
        any_match = False
        for kw in kws[keyword]:
            md = kw.md
            if _md_suitable_as_search_result(md):
                any_match = True
                if md not in md_priority:
                    md_priority[md] = kw.priority
                else:
                    md_priority[md] += kw.priority
        if any_match:
            if keyword not in keywords_good:
                keywords_good.append(keyword)
        else:
            keywords_bad.append(keyword)

    # this seems like we're over-logging but I'd like to see how people are
    # searching for a few weeks so we can tweak the algorithm used
    filtered_mds = _order_by_summed_md_priority(md_priority)
    for md in filtered_mds:
        if md.fw.vendor not in vendors:
            vendors.append(md.fw.vendor)
    _add_search_event(SearchEvent(value=request.args['value'],
                                  addr=_addr_hash(_get_client_address()),
                                  count=len(filtered_mds) + len(vendors),
                                  method='OR'))
    return render_template('search.html',
                           show_vendor_nag=True,
                           mds=filtered_mds[:max_results],
                           search_size=len(filtered_mds),
                           vendors=vendors,
                           keywords_good=keywords_good,
                           keywords_bad=keywords_bad)
