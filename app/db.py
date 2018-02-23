#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# Copyright (C) 2015-2018 Richard Hughes <richard@hughsie.com>
# Licensed under the GNU General Public License Version 2

from __future__ import print_function

from sqlalchemy import create_engine, func
from sqlalchemy.orm import scoped_session, sessionmaker
from sqlalchemy.ext.declarative import declarative_base

def _execute_count_star(q):
    count_query = q.statement.with_only_columns([func.count()]).order_by(None)
    return q.session.execute(count_query).scalar()

class Database(object):

    def __init__(self):
        self.engine = None
        self.session = None
        self.Base = None

    def init_app(self, app):

        # create the engine now the app is loaded
        self.engine = create_engine(app.config['DATABASE'], convert_unicode=True)
        self.engine.echo = app.testing
        self.session = scoped_session(sessionmaker(autocommit=False,
                                                   autoflush=False,
                                                   bind=self.engine))
        self.Base = declarative_base()
        self.Base.query = self.session.query_property()

    def modify_db(self):

        # get current schema version
        from .models import Setting, Report, _get_flat_dict_from_json, ReportAttribute
        setting = self.session.query(Setting).filter(Setting.key == 'db_schema_version').first()
        if not setting:
            print('Setting initial schema version')
            setting = Setting('db_schema_version', str(0))
            self.session.add(setting)

        if int(setting.value) == 19:
            print('Creating ReportAttribute table')
            self.Base.metadata.tables['report_attributes'].create(bind=self.engine, checkfirst=True)
            for r in self.session.query(Report).all():
                data = _get_flat_dict_from_json(r.unsed_json)
                del data['Created']
                del data['Modified']
                del data['BootTime']
                del data['UpdateState']
                del data['Checksum']
                if 'DeviceId' in data:
                    del data['DeviceId']
                for key in data:
                    self.session.add(ReportAttribute(r.report_id, key, data[key]))
            setting.value = 20
            print('Committing transaction')
            self.session.commit()
            return

        print('No schema changes required')

    def init_db(self):

        # ensure all tables exist
        self.Base.metadata.create_all(bind=self.engine)

        # ensure admin user exists
        from .models import User
        if not self.session.query(User).filter(User.username == 'admin').first():
            self.session.add(User(username='admin',
                                  password='5459dbe5e9aa80e077bfa40f3fb2ca8368ed09b4',
                                  display_name='Admin User',
                                  email='sign-test@fwupd.org',
                                  group_id='admin',
                                  is_enabled=True,
                                  is_qa=True,
                                  is_analyst=True))
            self.session.commit()

    def drop_db(self):

        # delete all tables
        self.Base.metadata.drop_all(bind=self.engine)
