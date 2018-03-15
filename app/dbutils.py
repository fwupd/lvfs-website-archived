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

def modify_db(db):

    # get current schema version
    from .models import Setting, User
    setting = db.session.query(Setting).filter(Setting.key == 'db_schema_version').first()
    if not setting:
        print('Setting initial schema version')
        setting = Setting('db_schema_version', str(0))
        db.session.add(setting)

    if int(setting.value) == 36:
        for u in db.session.query(User).all():
            if not u.unused_is_enabled:
                u.auth_type = None
                continue
            if u.unused_is_locked:
                u.auth_type = 'local+locked'
                continue
            u.auth_type = 'local'
            continue
        setting.value = 37
        db.session.commit()
        return

    # split a settings key
    if int(setting.value) == 37:
        print('Split sign_gpg_signing_uid')
        s1 = db.session.query(User).\
                filter(Setting.key == 'sign_gpg_signing_uid').first()
        if s1:
            s1.key = 'sign_gpg_firmware_uid'
            db.session.add(Setting('sign_gpg_metadata_uid', s1.value))
        setting.value = 38
        db.session.commit()
        return

    print('No schema changes required')
