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
        from .models import Setting, Event, FirmwareEvent, Firmware, User
        setting = self.session.query(Setting).filter(Setting.key == 'db_schema_version').first()
        if not setting:
            print('Setting initial schema version')
            setting = Setting('db_schema_version', str(0))
            self.session.add(setting)

        if int(setting.value) == 20:
            print('Creating firmware_events table')
            self.Base.metadata.tables['firmware_events'].create(bind=self.engine, checkfirst=True)
            setting.value = 21
            self.session.commit()
            return

        if int(setting.value) == 21:
            print('Getting all Firmwares')
            fws_checksum = {}
            fws_filename = {}
            for fw in self.session.query(Firmware).all():
                fws_checksum[fw.checksum_upload] = fw
                fws_filename[fw.filename] = fw
            print('Getting all Users')
            users = {}
            for user in self.session.query(User).all():
                users[user.username] = user
            print('Getting all Events')
            events = self.session.query(Event).order_by(Event.timestamp.asc()).all()
            print('Migrating content to events')
            for e in events:
                if e.message.startswith('Uploaded file'):
                    spl = e.message.split(' ')
                    if len(spl) != 5:
                        continue
                    filename = spl[2]
                    if filename not in fws_filename:
                        print('filename %s does not exist, skipping' % filename)
                        continue
                    if e.username not in users:
                        if e.username == 'dell':
                            user_id = users['dellqa'].user_id
                        else:
                            print('user %s does not exist, using admin' % e.username)
                            user_id = users['admin'].user_id
                    else:
                        user_id = users[e.username].user_id
                    fws_filename[filename].events.append(FirmwareEvent(spl[4], user_id, e.timestamp))

                elif e.message.startswith('Moved firmware'):
                    spl = e.message.split(' ')
                    if len(spl) != 5:
                        continue
                    checksum = spl[2]
                    if checksum not in fws_checksum:
                        print('firmware %s does not exist, skipping' % checksum)
                        continue
                    user_id = users[e.username].user_id
                    fws_checksum[checksum].events.append(FirmwareEvent(spl[4], user_id, e.timestamp))
            setting.value = 22
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
