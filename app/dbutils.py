#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# Copyright (C) 2015-2018 Richard Hughes <richard@hughsie.com>
# Licensed under the GNU General Public License Version 2
#
# pylint: disable=too-many-locals,too-many-statements,too-few-public-methods

from __future__ import print_function

from sqlalchemy import func

def _execute_count_star(q):
    count_query = q.statement.with_only_columns([func.count()]).order_by(None)
    return q.session.execute(count_query).scalar()

class Database(object):

    def __init__(self):
        self.Base = None

def init_db(db):

    # ensure all tables exist
    db.metadata.create_all(bind=db.engine)

    # ensure admin user exists
    from .models import User, Vendor
    if not db.session.query(User).filter(User.username == 'admin').first():
        vendor = Vendor('admin')
        vendor.display_name = 'Acme Corp.'
        vendor.description = 'A fake vendor used for testing firmware'
        db.session.add(vendor)
        db.session.commit()
        db.session.add(User(username='sign-test@fwupd.org',
                            password='5459dbe5e9aa80e077bfa40f3fb2ca8368ed09b4',
                            auth_type='local',
                            display_name='Admin User',
                            vendor_id=vendor.vendor_id,
                            is_admin=True,
                            is_qa=True,
                            is_analyst=True))
        db.session.commit()
    if not db.session.query(User).filter(User.username == 'anonymous').first():
        db.session.add(User(username='anonymous@fwupd.org',
                            display_name='Anonymous User',
                            vendor_id=1))
        db.session.commit()

def drop_db(db):
    db.metadata.drop_all(bind=db.engine)
