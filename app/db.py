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
        from .models import Setting, Component, Requirement, Firmware, Guid, EventLogItem
        setting = self.session.query(Setting).filter(Setting.key == 'db_schema_version').first()
        if not setting:
            print('Setting initial schema version')
            setting = Setting('db_schema_version', str(0))
            self.session.add(setting)
        print('Settings schema is currently version %s' % setting.value)

        # version 7 renames a table
        if int(setting.value) == 0:
            print('Renaming Components table')
            self.engine.execute('RENAME TABLE firmware_md TO components;')
            setting.value = 7
            self.session.commit()
            return

        # version 8 renames the appstream ID out of the way for v9
        if int(setting.value) == 7:
            print('Move the Component.id out the way')
            self.engine.execute('ALTER TABLE components CHANGE id appstream_id TEXT;')
            setting.value = 8
            self.session.commit()
            return

        # version 9 adds a new component_id key to Component and uses that as the primary key
        if int(setting.value) == 8:
            print('Create new Component primary key')
            self.engine.execute('ALTER TABLE components DROP PRIMARY KEY;')
            self.engine.execute('ALTER TABLE components ADD component_id INT NOT NULL PRIMARY KEY AUTO_INCREMENT;')
            setting.value = 9
            self.session.commit()
            return

        # version 10 splits out the requirements table
        if int(setting.value) == 9:
            print('Creating requirements table')
            self.Base.metadata.tables['requirements'].create(bind=self.engine, checkfirst=True)
            print('Migrating requirements from Component')
            for md in self.session.query(Component).all():
                if not md.unused_requirements:
                    continue
                for reqstr in md.unused_requirements.split(','):
                    tmp = reqstr.split('/')
                    if len(tmp) != 4:
                        continue
                    self.session.add(Requirement(md.component_id,
                                                 tmp[0], tmp[1],
                                                 tmp[2], tmp[3]))
            setting.value = 10
            self.session.commit()
            return

        # version 11 moves the container checksum to the firmware object
        if int(setting.value) == 10:
            print('Move the container checksum to Firmware')
            self.engine.execute('ALTER TABLE firmware ADD checksum VARCHAR(40) DEFAULT NULL;')
            print('Migrating checksums from Component')
            for fw in self.session.query(Firmware).all():
                fw.checksum = fw.mds[0].unused_checksum_container
            setting.value = 11
            self.session.commit()
            return

        # version 12 splits out the GUID table
        if int(setting.value) == 11:
            print('Creating GUIDs table')
            self.Base.metadata.tables['guids'].create(bind=self.engine, checkfirst=True)
            print('Migrating GUIDs from Component')
            for md in self.session.query(Component).all():
                if not md.unused_guid:
                    continue
                for guid in md.unused_guid.split(','):
                    self.session.add(Guid(md.component_id, guid))
            setting.value = 12
            self.session.commit()
            return

        # version 13 adds the uploader username to the firmware table
        if int(setting.value) == 12:
            print('Adding username to Firmware table')
            self.engine.execute('ALTER TABLE firmware ADD username VARCHAR(40) DEFAULT NULL;')
            setting.value = 14
            self.session.commit()
            return

        # version 14 migrates the username using the event log
        if int(setting.value) == 13:
            print('Fixing username for each Firmware entry using event log')
            for fw in self.session.query(Firmware).all():
                msgtxt = 'Uploaded file ' + fw.firmware_id + '%'
                ev = self.session.query(EventLogItem).\
                            filter(EventLogItem.message.like(msgtxt)).\
                            order_by(EventLogItem.id.desc()).first()
                if not ev:
                    print('Failed to get owner for %s' % fw.firmware_id)
                    continue
                fw.username = ev.username
            setting.value = 14
            self.session.commit()
            return

        print('No schema changes required')

        # next version can remove md.unused_requirements, md.unused_checksum and md.unused_guid
        #self.engine.execute('ALTER TABLE components DROP COLUMN requirements;')
        #self.engine.execute('ALTER TABLE components DROP COLUMN checksum_container;')
        #self.engine.execute('ALTER TABLE components DROP COLUMN guid;')

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
