#!/usr/bin/python2
# -*- coding: utf-8 -*-
#
# Copyright (C) 2017 Richard Hughes <richard@hughsie.com>
# Licensed under the GNU General Public License Version 2

from flask import request, flash, url_for, redirect, render_template, g
from flask_login import login_required

from app import app, db

from .util import _event_log, _error_permission_denied
from .models import UserCapability

# sort by awesomeness
def _sort_vendor_func(a, b):
    a_val = a._get_sorting_key()
    b_val = b._get_sorting_key()
    if a_val > b_val:
        return -1
    if a_val < b_val:
        return 1
    return 0

@app.route('/status')
@app.route('/vendorlist') # deprecated
@app.route('/lvfs/vendorlist')
def vendor_list():
    vendors = db.vendors.get_all()
    vendors.sort(_sort_vendor_func)
    return render_template('vendorlist.html', vendors=vendors)

@app.route('/lvfs/vendorlist/add', methods=['GET', 'POST'])
@login_required
def vendor_add():
    """ Add a vendor [ADMIN ONLY] """

    # only accept form data
    if request.method != 'POST':
        return redirect(url_for('.vendor_list'))

    # security check
    if not g.user.check_capability(UserCapability.Admin):
        return _error_permission_denied('Unable to add vendor as non-admin')

    if not 'group_id' in request.form:
        return _error_permission_denied('Unable to add vendor as no data')
    if db.vendors.get_item(request.form['group_id']):
        flash('Already a vendor with that group ID', 'warning')
        return redirect(url_for('.vendor_list'), 302)
    db.vendors.add(request.form['group_id'])

    _event_log("Created vendor %s" % request.form['group_id'])
    flash('Added vendor', 'info')
    return redirect(url_for('.vendor_details', group_id=request.form['group_id']), 302)

@app.route('/lvfs/vendor/<group_id>/delete')
@login_required
def vendor_delete(group_id):
    """ Removes a vendor [ADMIN ONLY] """

    # security check
    if not g.user.check_capability(UserCapability.Admin):
        return _error_permission_denied('Unable to remove vendor as non-admin')
    if not db.vendors.get_item(group_id):
        flash('No a vendor with that group ID', 'warning')
        return redirect(url_for('.vendor_list'), 302)
    db.vendors.remove(group_id)

    _event_log("Removed vendor %s" % group_id)
    flash('Removed vendor', 'info')
    return redirect(url_for('.vendor_list'), 302)

@app.route('/lvfs/vendor/<group_id>/details')
@login_required
def vendor_details(group_id):
    """ Allows changing a vendor [ADMIN ONLY] """

    # security check
    if not g.user.check_capability(UserCapability.Admin):
        return _error_permission_denied('Unable to edit vendor as non-admin')
    vendor = db.vendors.get_item(group_id)
    if not vendor:
        flash('No a vendor with that group ID', 'warning')
        return redirect(url_for('.vendor_list'), 302)
    return render_template('vendor-details.html', v=vendor)


@app.route('/lvfs/vendor/<group_id>/modify_by_admin', methods=['GET', 'POST'])
@login_required
def vendor_modify_by_admin(group_id):
    """ Change details about the any vendor """

    # only accept form data
    if request.method != 'POST':
        return redirect(url_for('.vendor_list'))

    # security check
    if not g.user.check_capability(UserCapability.Admin):
        return _error_permission_denied('Unable to modify vendor as non-admin')

    # don't set the optional password
    db.vendors.modify(group_id,
                      request.form['display_name'],
                      request.form['plugins'],
                      request.form['description'],
                      request.form['visible'],
                      request.form['is_fwupd_supported'],
                      request.form['is_account_holder'],
                      request.form['is_uploading'],
                      request.form['comments'])

    _event_log('Changed vendor %s properties' % group_id)
    flash('Updated vendor', 'info')
    return redirect(url_for('.vendor_list'))
