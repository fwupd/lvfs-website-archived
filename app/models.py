#!/usr/bin/python2
# -*- coding: utf-8 -*-
#
# Copyright (C) 2015-2018 Richard Hughes <richard@hughsie.com>
# Licensed under the GNU General Public License Version 2
#
# pylint: disable=too-few-public-methods,too-many-instance-attributes

import datetime

from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey, Index
from sqlalchemy.orm import relationship

from app import db

class UserCapability(object):
    Admin = 'admin'
    QA = 'qa'
    Analyst = 'analyst'
    User = 'user'

class User(db.Base):

    # database
    __tablename__ = 'users'
    username = Column(String(40), primary_key=True, nullable=False, unique=True, default='')
    password = Column(String(40), nullable=False, default='')
    display_name = Column(String(128))
    email = Column(String(255))
    group_id = Column(String(40), nullable=False)
    is_enabled = Column(Boolean, default=False)
    is_qa = Column(Boolean, default=False)
    is_analyst = Column(Boolean, default=False)
    is_locked = Column(Boolean, default=False)

    def __init__(self, username, password=None, display_name=None, email=None,
                 group_id=None, is_enabled=True, is_analyst=False, is_qa=False, is_locked=False):
        """ Constructor for object """
        self.username = username
        self.password = password
        self.display_name = display_name
        self.email = email
        self.is_enabled = is_enabled
        self.is_analyst = is_analyst
        self.is_qa = is_qa
        self.group_id = group_id
        self.is_locked = is_locked

    def check_group_id(self, group_id):

        # admin can see everything
        if self.group_id == 'admin':
            return True

        # typically used when checking if a vendor can delete firmware
        if self.group_id == group_id:
            return True

        # something else
        return False

    def check_capability(self, required_auth_level):

        # user has been disabled for bad behaviour
        if not self.is_enabled:
            return False

        # admin only
        if required_auth_level == UserCapability.Admin:
            if self.group_id == 'admin':
                return True
            return False

        # analysts only
        if required_auth_level == UserCapability.Analyst:
            if self.group_id == 'admin':
                return True
            if self.is_qa:
                return True
            if self.is_analyst:
                return True
            return False

        # QA only
        if required_auth_level == UserCapability.QA:
            if self.group_id == 'admin':
                return True
            if self.is_qa:
                return True
            return False

        # any action that just requires to be logged in
        if required_auth_level == UserCapability.User:
            return True

        # something else
        return False

    @property
    def is_authenticated(self):
        return True

    @property
    def is_active(self):
        return True

    @property
    def is_anonymous(self):
        return False

    def get_id(self):
        return str(self.username)

    def __repr__(self):
        return "User object %s" % self.username

class Group(db.Base):

    # sqlalchemy metadata
    __tablename__ = 'groups'
    group_id = Column(String(40), primary_key=True, unique=True)
    _vendor_ids = Column('vendor_ids', String(40), nullable=False, default='')

    def __init__(self, group_id=None):
        """ Constructor for object """
        self.group_id = group_id
        self._vendor_ids = ''
        self.vendor_ids = []

    @property
    def vendor_ids(self):
        if not len(self._vendor_ids):
            return []
        return self._vendor_ids.split(',')

    @vendor_ids.setter
    def vendor_ids(self, value):
        self._vendor_ids = ','.join(value)

    def __repr__(self):
        return "Group object %s" % self.group_id

class Vendor(db.Base):

    # sqlalchemy metadata
    __tablename__ = 'vendors'
    group_id = Column(String(40), primary_key=True, nullable=False, unique=True, default='')
    display_name = Column(String(128), nullable=False, default='')
    plugins = Column(String(128), nullable=False, default='')
    description = Column(String(255), nullable=False, default='')
    visible = Column(Boolean, default=False)
    is_fwupd_supported = Column(String(16), nullable=False, default='no')
    is_account_holder = Column(String(16), nullable=False, default='no')
    is_uploading = Column(String(16), nullable=False, default='no')
    comments = Column(String(255), nullable=False, default='')

    def __init__(self, group_id=None):
        """ Constructor for object """
        self.group_id = group_id
        self.display_name = None
        self.plugins = None
        self.description = None
        self.visible = False
        self.is_fwupd_supported = None
        self.is_account_holder = None
        self.is_uploading = None
        self.comments = None

    def get_sort_key(self):
        val = 0
        if self.is_fwupd_supported == 'yes':
            val += 0x200
        if self.is_fwupd_supported == 'na':
            val += 0x100
        if self.is_account_holder == 'yes':
            val += 0x20
        if self.is_account_holder == 'na':
            val += 0x10
        if self.is_uploading == 'yes':
            val += 0x2
        if self.is_uploading == 'na':
            val += 0x1
        return val

    def __repr__(self):
        return "Vendor object %s" % self.group_id

class EventLogItem(db.Base):

    # sqlalchemy metadata
    __tablename__ = 'event_log'
    id = Column(Integer, primary_key=True, nullable=False, unique=True)
    timestamp = Column(DateTime, nullable=False, default=datetime.datetime.utcnow)
    username = Column(String(40), nullable=False, default='')
    group_id = Column(String(40), nullable=False)
    address = Column('addr', String(40), nullable=False)
    message = Column(Text)
    is_important = Column(Integer, default=0)
    request = Column(Text)

    def __init__(self, username=None, group_id=None, address=None, message=None,
                 request=None, is_important=False):
        """ Constructor for object """
        self.timestamp = None
        self.username = username
        self.group_id = group_id
        self.address = address
        self.message = message
        self.request = request
        self.is_important = is_important
    def __repr__(self):
        return "EventLogItem object %s" % self.message

class Requirement(db.Base):

    # sqlalchemy metadata
    __tablename__ = 'requirements'
    requirement_id = Column(Integer, primary_key=True, unique=True)
    component_id = Column(Integer, ForeignKey('components.component_id'), nullable=False)
    kind = Column(Text, nullable=False)
    value = Column(Text, nullable=False)
    compare = Column(Text)
    version = Column(Text)

    # link back to parent
    md = relationship("Component", back_populates="requirements")

    def __init__(self, component_id=None, kind=None, value=None, compare=None, version=None):
        """ Constructor for object """
        self.kind = kind        # e.g. 'id', 'firmware' or 'hardware'
        self.value = value      # e.g. 'bootloader' or 'org.freedesktop.fwupd'
        self.compare = compare
        self.version = version
        self.component_id = component_id

    def __repr__(self):
        return "Requirement object %s/%s/%s/%s" % (self.kind, self.value, self.compare, self.version)

class Guid(db.Base):

    # sqlalchemy metadata
    __tablename__ = 'guids'
    guid_id = Column(Integer, primary_key=True, unique=True, nullable=False)
    component_id = Column(Integer, ForeignKey('components.component_id'), nullable=False)
    value = Column(Text)

    # link back to parent
    md = relationship("Component", back_populates="guids")

    def __init__(self, component_id=None, value=None):
        """ Constructor for object """
        #self.guid_id = 0
        self.component_id = component_id
        self.value = value

    def __repr__(self):
        return "Guid object %s" % self.guid_id

class Component(db.Base):

    # sqlalchemy metadata
    __tablename__ = 'components'
    component_id = Column(Integer, primary_key=True, unique=True, nullable=False)
    firmware_id = Column(String(40), ForeignKey('firmware.firmware_id'), nullable=False)
    metainfo_id = Column(String(40), nullable=False)
    checksum_contents = Column(String(40), nullable=False)
    unused_checksum_container = Column('checksum_container', String(40))
    appstream_id = Column(Text)
    name = Column(Text)
    summary = Column(Text)
    unused_guid = Column('guid', Text)
    description = Column(Text)
    release_description = Column(Text)
    url_homepage = Column(Text)
    metadata_license = Column(Text)
    project_license = Column(Text)
    developer_name = Column(Text)
    filename_contents = Column(Text)
    release_timestamp = Column(Integer, default=0)
    version = Column(String(255))
    release_installed_size = Column(Integer, default=0)
    release_download_size = Column(Integer, default=0)
    release_urgency = Column(String(16))
    screenshot_url = Column(Text)
    screenshot_caption = Column(Text)
    unused_requirements = Column('requirements', Text)

    # link back to parent
    fw = relationship("Firmware", back_populates="mds")

    # include all Component objects
    requirements = relationship("Requirement", back_populates="md")
    guids = relationship("Guid", back_populates="md")

    def __init__(self):
        """ Constructor for object """
        self.firmware_id = None             # this maps the object back to Firmware
        self.appstream_id = None            # e.g. com.hughski.ColorHug.firmware
        self.guids = []
        self.version = None
        self.name = None
        self.summary = None
        self.checksum_contents = None       # SHA1 of the firmware.bin
        self.release_description = None
        self.release_timestamp = 0
        self.developer_name = None
        self.metadata_license = None
        self.project_license = None
        self.url_homepage = None
        self.description = None
        self.filename_contents = None       # filename of the firmware.bin
        self.release_installed_size = 0
        self.release_download_size = 0
        self.release_urgency = None
        self.screenshot_url = None
        self.screenshot_caption = None
        self.metainfo_id = None              # SHA1 of the metainfo.xml file

    def find_req(self, kind=None, value=None):
        """ Find a Requirement from the kind and/or value """
        for rq in self.requirements:
            if kind and rq.kind != kind:
                continue
            if value and rq.value != value:
                continue
            return rq
        return None

    def __repr__(self):
        return "Component object %s" % self.firmware_id

class Firmware(db.Base):

    # sqlalchemy metadata
    __tablename__ = 'firmware'
    group_id = Column(String(40), nullable=False)
    addr = Column(String(40), nullable=False)
    timestamp = Column(DateTime, nullable=False, default=datetime.datetime.utcnow)
    filename = Column(String(255), nullable=False)
    download_cnt = Column(Integer, default=0)
    firmware_id = Column(String(40), primary_key=True, unique=True)
    version_display = Column(String(255), nullable=True, default=None)
    target = Column(String(255), nullable=False)
    checksum = Column(String(40), nullable=False)

    # include all Component objects
    mds = relationship("Component", back_populates="fw")

    def __init__(self):
        """ Constructor for object """
        self.group_id = None
        self.addr = None
        self.timestamp = None
        self.filename = None        # filename of the original .cab file
        self.firmware_id = None     # SHA1 of the original .cab file
        self.target = None          # pivate, embargo, testing, etc.
        self.version_display = None # from the firmware.inf file
        self.download_cnt = 0       # generated from the client database
        self.checksum = None        # SHA1 of the signed .cab
        self.mds = []

    def __repr__(self):
        return "Firmware object %s" % self.firmware_id

class Client(db.Base):

    # sqlalchemy metadata
    __tablename__ = 'clients'
    id = Column(Integer, primary_key=True, nullable=False, unique=True)
    timestamp = Column(DateTime, nullable=False, default=datetime.datetime.utcnow)
    addr = Column(String(40), nullable=False)
    filename = Column(String(256), index=True)
    user_agent = Column(String(256), default=None)

    # create indexes
    Index('idx_filename', 'filename', unique=True)

    def __init__(self, addr=None, filename=None, user_agent=None, timestamp=None):
        """ Constructor for object """
        self.id = 0
        self.timestamp = timestamp
        self.addr = addr
        self.filename = filename
        self.user_agent = user_agent

    def __repr__(self):
        return "Client object %s" % self.id

class Report(db.Base):

    # sqlalchemy metadata
    __tablename__ = 'reports'
    id = Column(Integer, primary_key=True, nullable=False, unique=True)
    timestamp = Column(DateTime, nullable=False, default=datetime.datetime.utcnow)
    state = Column(Integer, default=0)
    json = Column(Text)
    machine_id = Column(String(64), nullable=False)
    firmware_id = Column(String(40), nullable=False)
    checksum = Column(String(64), nullable=False)

    def __init__(self, firmware_id=None, machine_id=None, state=0, checksum=None, json=None):
        """ Constructor for object """
        self.id = 0
        self.timestamp = None
        self.state = state
        self.json = json
        self.machine_id = machine_id
        self.firmware_id = firmware_id
        self.checksum = checksum
    def __repr__(self):
        return "Report object %s" % self.id

class Setting(db.Base):

    # sqlalchemy metadata
    __tablename__ = 'settings'
    key = Column('config_key', Text, primary_key=True)
    value = Column('config_value', Text)

    def __init__(self, key, value=None):
        """ Constructor for object """
        self.key = key
        self.value = value
    def __repr__(self):
        return "Setting object %s" % self.key

def _get_datestr_from_datetime(when):
    return int("%04i%02i%02i" % (when.year, when.month, when.day))

class Analytic(db.Base):

    # sqlalchemy metadata
    __tablename__ = 'analytics'
    datestr = Column(Integer, primary_key=True, default=0)
    kind = Column(Integer, primary_key=True, default=0)
    cnt = Column(Integer, default=1)

    def __init__(self, kind, timestamp=datetime.date.today()):
        """ Constructor for object """
        self.kind = kind
        self.cnt = 1
        self.datestr = _get_datestr_from_datetime(timestamp)

    def __repr__(self):
        return "Analytic object %i:%s" % (self.kind, self.datestr)

class DownloadKind(object):
    METADATA = 0
    FIRMWARE = 1
    SIGNING = 2
