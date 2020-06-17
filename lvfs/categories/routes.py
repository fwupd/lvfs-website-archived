#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2019 Richard Hughes <richard@hughsie.com>
#
# SPDX-License-Identifier: GPL-2.0+

from flask import Blueprint, request, url_for, redirect, flash, render_template
from flask_login import login_required

from lvfs import db

from lvfs.models import Category
from lvfs.util import admin_login_required
from lvfs.util import _error_internal

bp_categories = Blueprint('categories', __name__, template_folder='templates')

@bp_categories.route('/')
@login_required
@admin_login_required
def route_list():
    categories = db.session.query(Category).order_by(Category.category_id.asc()).all()
    return render_template('category-list.html',
                           category='admin',
                           categories=categories)

@bp_categories.route('/create', methods=['POST'])
@login_required
@admin_login_required
def route_create():
    # ensure has enough data
    if 'value' not in request.form:
        return _error_internal('No form data found!')
    value = request.form['value']
    if not value or not value.startswith('X-') or value.find(' ') != -1:
        flash('Failed to add category: Value needs to be a valid group name', 'warning')
        return redirect(url_for('categories.route_list'))

    # already exists
    if db.session.query(Category).filter(Category.value == value).first():
        flash('Failed to add category: The category already exists', 'info')
        return redirect(url_for('categories.route_list'))

    # add category
    cat = Category(value=request.form['value'])
    db.session.add(cat)
    db.session.commit()
    flash('Added category', 'info')
    return redirect(url_for('categories.route_show', category_id=cat.category_id))

@bp_categories.route('/<int:category_id>/delete', methods=['POST'])
@login_required
@admin_login_required
def route_delete(category_id):

    # get category
    cat = db.session.query(Category).\
            filter(Category.category_id == category_id).first()
    if not cat:
        flash('No category found', 'info')
        return redirect(url_for('categories.route_list'))

    # delete
    db.session.delete(cat)
    db.session.commit()
    flash('Deleted category', 'info')
    return redirect(url_for('categories.route_list'))

@bp_categories.route('/<int:category_id>/modify', methods=['POST'])
@login_required
@admin_login_required
def route_modify(category_id):

    # find category
    cat = db.session.query(Category).\
                filter(Category.category_id == category_id).first()
    if not cat:
        flash('No category found', 'info')
        return redirect(url_for('categories.route_list'))

    # modify category
    cat.expect_device_checksum = bool('expect_device_checksum' in request.form)
    for key in ['name', 'fallbacks']:
        if key in request.form:
            setattr(cat, key, request.form[key])
    db.session.commit()

    # success
    flash('Modified category', 'info')
    return redirect(url_for('categories.route_show', category_id=category_id))

@bp_categories.route('/<int:category_id>')
@login_required
@admin_login_required
def route_show(category_id):

    # find category
    cat = db.session.query(Category).\
            filter(Category.category_id == category_id).first()
    if not cat:
        flash('No category found', 'info')
        return redirect(url_for('categories.route_list'))

    # show details
    return render_template('category-details.html',
                           category='admin',
                           cat=cat)
