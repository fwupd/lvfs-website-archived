#!/usr/bin/python2
# -*- coding: utf-8 -*-
#
# Copyright (C) 2018 Richard Hughes <richard@hughsie.com>
# Licensed under the GNU General Public License Version 2

from __future__ import print_function

from flask import request, render_template

from app import app, db

from .models import Keyword, Vendor, _split_search_string
from .util import _event_log

def _md_suitable_as_search_result(md):
    if not md:
        return False
    if md.fw.target != 'stable' and md.fw.target != 'testing':
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

    # get any vendor information
    vendors = []
    for vendor in db.session.query(Vendor).all():
        if not vendor.visible:
            continue
        for keyword in _split_search_string(vendor.display_name):
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
            if md_priority[keyword] > priority_max:
                priority_max = md_priority[keyword]
        if found_in_all:
            md_priority_in_all[md] = priority_max
    if len(md_priority_in_all) > 0:
        filtered_mds = _order_by_summed_md_priority(md_priority_in_all)
        # this seems like we're over-logging but I'd like to see how people are
        # searching for a few weeks so we can tweak the algorithm used
        _event_log('User search for "%s" returned %i AND results' %
                   (request.args['value'], len(filtered_mds)))
        return render_template('search.html',
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
    _event_log('User search for "%s" returned %i OR results' %
               (request.args['value'], len(filtered_mds)))
    return render_template('search.html',
                           mds=filtered_mds[:max_results],
                           search_size=len(filtered_mds),
                           vendors=vendors,
                           keywords_good=keywords_good,
                           keywords_bad=keywords_bad)
