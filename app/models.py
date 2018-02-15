#!/usr/bin/python2
# -*- coding: utf-8 -*-
#
# Copyright (C) 2015-2018 Richard Hughes <richard@hughsie.com>
# Licensed under the GNU General Public License Version 2
#
# pylint: disable=too-few-public-methods,too-many-instance-attributes

import datetime
import fnmatch
import re
import json

from gi.repository import AppStreamGlib

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

    def check_for_issue(self, issue, readonly=False):

        # locked accounts can never see issues
        if not self.is_enabled:
            return False

        # anyone in the admin group can see everything
        if self.group_id == 'admin':
            return True

        # any issues owned by admin can be viewed by a QA user
        if self.is_qa and issue.group_id == 'admin' and readonly:
            return True

        # QA user can modify any issues matching group_id
        if self.is_qa and self.group_id == issue.group_id:
            return True

        # something else
        return False

    def check_for_firmware(self, fw, readonly=False):

        # locked accounts can never see firmware
        if not self.is_enabled:
            return False

        # anyone in the admin group can see everything
        if self.group_id == 'admin':
            return True

        # QA user can modify any firmware matching group_id
        if self.is_qa and self.group_id == fw.group_id:
            return True

        # Analyst user can view (but not modify) any firmware matching group_id
        if readonly and self.is_analyst and self.group_id == fw.group_id:
            return True

        # User can see firmwares in the group owned by them
        if self.group_id == fw.group_id and self.username == fw.username:
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

class Event(db.Base):

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
        return "Event object %s" % self.message

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
    appstream_id = Column(Text)
    name = Column(Text)
    summary = Column(Text)
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
    username = Column(String(40), default=None)

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
        self.username = None        # username of the uploader
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
        self.timestamp = timestamp
        self.addr = addr
        self.filename = filename
        self.user_agent = user_agent

    def __repr__(self):
        return "Client object %s" % self.id

class Condition(db.Base):

    # sqlalchemy metadata
    __tablename__ = 'conditions'
    condition_id = Column(Integer, primary_key=True, nullable=False, unique=True)
    issue_id = Column(Integer, ForeignKey('issues.issue_id'), nullable=False)
    key = Column(Text)
    value = Column(Text)
    compare = Column(Text, default='eq', nullable=False)

    # link back to parent
    issue = relationship("Issue", back_populates="conditions")

    def matches(self, value):
        if self.compare == 'eq':
            return value == self.value
        if self.compare == 'lt':
            return AppStreamGlib.utils_vercmp(value, self.value) < 0
        if self.compare == 'le':
            return AppStreamGlib.utils_vercmp(value, self.value) <= 0
        if self.compare == 'gt':
            return AppStreamGlib.utils_vercmp(value, self.value) > 0
        if self.compare == 'ge':
            return AppStreamGlib.utils_vercmp(value, self.value) >= 0
        if self.compare == 'glob':
            return fnmatch.fnmatch(value, self.value)
        if self.compare == 'regex':
            return re.search(self.value, value)
        return False

    @property
    def relative_cost(self):
        if self.compare == 'eq':
            return 0
        if self.compare in ['lt', 'le', 'gt', 'ge']:
            return 1
        if self.compare == 'glob':
            return 5
        if self.compare == 'regex':
            return 10
        return False

    def __init__(self, issue_id=0, key=None, value=None, compare='eq'):
        """ Constructor for object """
        self.issue_id = issue_id
        self.key = key
        self.value = value
        self.compare = compare

    def __repr__(self):
        return "Condition object %s %s %s" % (self.key, self.compare, self.value)

class Issue(db.Base):

    # sqlalchemy metadata
    __tablename__ = 'issues'
    issue_id = Column(Integer, primary_key=True, nullable=False, unique=True)
    priority = Column(Integer)
    enabled = Column(Boolean, default=False)
    group_id = Column(Text, default=None)
    url = Column(Text, default='')
    name = Column(Text)
    description = Column(Text, default='')
    conditions = relationship("Condition", back_populates="issue")

    def __init__(self, url=None, name=None, description=None, enabled=False, group_id=None, priority=0):
        """ Constructor for object """
        self.url = url
        self.name = name
        self.enabled = enabled
        self.priority = priority
        self.description = description
        self.enabled = enabled
        self.group_id = group_id
        self.priority = priority

    def matches(self, data):
        """ if all conditions are satisfied from data """
        for condition in sorted(self.conditions, key=lambda x: x.relative_cost):
            if not condition.key in data:
                return False
            if not condition.matches(data[condition.key]):
                return False
        return True

    def __repr__(self):
        return "Issue object %s" % self.url

def _get_flat_dict_from_json(txt):
    data = {}
    items = json.loads(txt)
    for key in items:
        if key == 'Metadata':
            items2 = items[key]
            for key2 in items2:
                data[key2] = items2[key2]
            continue
        data[key] = items[key]
    return data

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
    issue_id = Column(Integer, default=0)

    def __init__(self, firmware_id=None, machine_id=None, state=0, checksum=None, json_raw=None, issue_id=0):
        """ Constructor for object """
        self.timestamp = None
        self.state = state
        self.json = json_raw
        self.machine_id = machine_id
        self.firmware_id = firmware_id
        self.issue_id = issue_id
        self.checksum = checksum

    def to_flat_dict(self):
        return _get_flat_dict_from_json(self.json)

    def __repr__(self):
        return "Report object %s" % self.id

class Setting(db.Base):

    # sqlalchemy metadata
    __tablename__ = 'settings'
    setting_id = Column(Integer, primary_key=True, nullable=False, unique=True)
    key = Column('config_key', Text)
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

    def __init__(self, kind, datestr=0):
        """ Constructor for object """
        self.kind = kind
        self.cnt = 1
        self.datestr = datestr

    def __repr__(self):
        return "Analytic object %i:%s" % (self.kind, self.datestr)

class Useragent(db.Base):

    # sqlalchemy metadata
    __tablename__ = 'useragents'
    condition_id = Column(Integer, primary_key=True, nullable=False, unique=True)
    datestr = Column(Integer, default=0)
    value = Column(Text, default=None)
    cnt = Column(Integer, default=1)

    def __init__(self, value, datestr=0, cnt=1):
        """ Constructor for object """
        self.value = value
        self.cnt = cnt
        self.datestr = datestr

    def __repr__(self):
        return "Useragent object %i:%s" % (self.kind, self.datestr)

class DownloadKind(object):
    METADATA = 0
    FIRMWARE = 1
    SIGNING = 2
