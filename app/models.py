#!/usr/bin/python2
# -*- coding: utf-8 -*-
#
# Copyright (C) 2015-2018 Richard Hughes <richard@hughsie.com>
# Licensed under the GNU General Public License Version 2
#
# pylint: disable=too-few-public-methods,too-many-instance-attributes,too-many-arguments

import datetime
import fnmatch
import re

from gi.repository import AppStreamGlib

from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey, Index
from sqlalchemy.orm import relationship
from sqlalchemy.dialects import mysql

from app import db

class UserCapability(object):
    Admin = 'admin'
    VendorManager = 'vendor-manager'
    QA = 'qa'
    Analyst = 'analyst'
    User = 'user'

class User(db.Model):

    # database
    __tablename__ = 'users'
    __table_args__ = (
        Index("idx_username_password", "username", "password"),
        )
    user_id = Column(Integer, primary_key=True)
    username = Column(String(80), nullable=False)
    username_old = Column(Text, default=None)
    password = Column(mysql.BINARY(40), default=None)
    display_name = Column(Text, default=None)
    vendor_id = Column(Integer, ForeignKey('vendors.vendor_id'), nullable=False)
    auth_type = Column(Text, default='disabled')
    is_qa = Column(Boolean, default=False)
    is_analyst = Column(Boolean, default=False)
    is_vendor_manager = Column(Boolean, default=False)
    is_admin = Column(Boolean, default=False)

    # link using foreign keys
    vendor = relationship('Vendor', foreign_keys=[vendor_id])

    def __init__(self, username, password=None, display_name=None,
                 vendor_id=None, auth_type='disabled', is_analyst=False, is_qa=False,
                 is_admin=False, is_vendor_manager=False):
        """ Constructor for object """
        self.username = username
        self.password = password
        self.display_name = display_name
        self.auth_type = auth_type
        self.is_analyst = is_analyst
        self.is_qa = is_qa
        self.vendor_id = vendor_id
        self.is_admin = is_admin
        self.is_vendor_manager = is_vendor_manager

    def check_for_issue(self, issue, readonly=False):

        # disabled accounts can never see issues
        if not self.auth_type:
            return False

        # anyone who is an admin can see everything
        if self.is_admin:
            return True

        # any issues owned by admin can be viewed by a QA user
        if self.is_qa and issue.vendor_id == 1 and readonly:
            return True

        # QA user can modify any issues matching group_id
        if self.is_qa and self.vendor_id == issue.vendor_id:
            return True

        # something else
        return False

    def check_for_firmware(self, fw, readonly=False):

        # disabled accounts can never see firmware
        if not self.auth_type:
            return False

        # anyone in the admin group can see everything
        if self.is_admin:
            return True

        # QA user can modify any firmware matching vendor_id
        if self.is_qa and self.vendor_id == fw.vendor_id:
            return True

        # Analyst user can view (but not modify) any firmware matching vendor_id
        if readonly and self.is_analyst and self.vendor_id == fw.vendor_id:
            return True

        # User can see firmwares in the group owned by them
        if self.vendor_id == fw.vendor_id and self.user_id == fw.user_id:
            return True

        # something else
        return False

    def check_for_vendor(self, vendor):

        # disabled accounts can never see firmware
        if not self.auth_type:
            return False

        # anyone in the admin group can see everything
        if self.is_admin:
            return True

        # manager user can modify any firmware matching vendor_id
        if self.is_vendor_manager and self.vendor_id == vendor.vendor_id:
            return True

        # something else
        return False

    def check_capability(self, required_auth_level):

        # user has been disabled for bad behaviour
        if not self.auth_type:
            return False

        # admin only
        if required_auth_level == UserCapability.Admin:
            if self.is_admin:
                return True
            return False

        # vendor manager only
        if required_auth_level == UserCapability.VendorManager:
            if self.is_admin:
                return True
            if self.is_vendor_manager:
                return True
            return False

        # analysts only
        if required_auth_level == UserCapability.Analyst:
            if self.is_admin:
                return True
            if self.is_qa:
                return True
            if self.is_analyst:
                return True
            return False

        # QA only
        if required_auth_level == UserCapability.QA:
            if self.is_admin:
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

class Restriction(db.Model):

    # sqlalchemy metadata
    __tablename__ = 'restrictions'
    restriction_id = Column(Integer, primary_key=True, unique=True, nullable=False)
    vendor_id = Column(Integer, ForeignKey('vendors.vendor_id'), nullable=False)
    value = Column(Text, nullable=False)

    # link back to parent
    vendor = relationship("Vendor", back_populates="restrictions")

    def __init__(self, value=None):
        """ Constructor for object """
        self.value = value

    def __repr__(self):
        return "Restriction object %s" % self.restriction_id

class Vendor(db.Model):

    # sqlalchemy metadata
    __tablename__ = 'vendors'
    vendor_id = Column(Integer, primary_key=True, unique=True)
    group_id = Column(Text, nullable=False, index=True)
    display_name = Column(Text, default=None)
    plugins = Column(Text, default=None)
    description = Column(Text, default=None)
    visible = Column(Boolean, default=False)
    visible_for_search = Column(Boolean, default=False)
    is_fwupd_supported = Column(String(16), nullable=False, default='no')
    is_account_holder = Column(String(16), nullable=False, default='no')
    is_uploading = Column(String(16), nullable=False, default='no')
    comments = Column(Text, default=None)
    icon = Column(Text, default=None)
    keywords = Column(Text, default=None)
    oauth_unknown_user = Column(Text, default=None)
    oauth_domain_glob = Column(Text, default=None)
    remote_id = Column(Integer, ForeignKey('remotes.remote_id'), nullable=False)

    # magically get the users in this vendor group
    users = relationship("User", back_populates="vendor")
    restrictions = relationship("Restriction", back_populates="vendor")

    # link using foreign keys
    remote = relationship('Remote', foreign_keys=[remote_id])

    def __init__(self, group_id=None, remote_id=None):
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
        self.icon = None
        self.keywords = None
        self.remote_id = remote_id

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

class Event(db.Model):

    # sqlalchemy metadata
    __tablename__ = 'event_log'
    id = Column(Integer, primary_key=True, nullable=False, unique=True)
    timestamp = Column(DateTime, nullable=False, default=datetime.datetime.utcnow)
    user_id = Column(Integer, ForeignKey('users.user_id'), nullable=False)
    vendor_id = Column(Integer, ForeignKey('vendors.vendor_id'), nullable=False)
    address = Column('addr', String(40), nullable=False)
    message = Column(Text, default=None)
    is_important = Column(Integer, default=0)
    request = Column(Text, default=None)

    # link using foreign keys
    vendor = relationship('Vendor', foreign_keys=[vendor_id])
    user = relationship('User', foreign_keys=[user_id])

    def __init__(self, user_id, vendor_id=None, address=None, message=None,
                 request=None, is_important=False):
        """ Constructor for object """
        self.timestamp = None
        self.user_id = user_id
        self.vendor_id = vendor_id
        self.address = address
        self.message = message
        self.request = request
        self.is_important = is_important
    def __repr__(self):
        return "Event object %s" % self.message

class Requirement(db.Model):

    # sqlalchemy metadata
    __tablename__ = 'requirements'
    requirement_id = Column(Integer, primary_key=True, unique=True)
    component_id = Column(Integer, ForeignKey('components.component_id'), nullable=False)
    kind = Column(Text, nullable=False)
    value = Column(Text, default=None)
    compare = Column(Text, default=None)
    version = Column(Text, default=None)

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

class Guid(db.Model):

    # sqlalchemy metadata
    __tablename__ = 'guids'
    guid_id = Column(Integer, primary_key=True, unique=True, nullable=False)
    component_id = Column(Integer, ForeignKey('components.component_id'), nullable=False)
    value = Column(Text, nullable=False)

    # link back to parent
    md = relationship("Component", back_populates="guids")

    def __init__(self, component_id=None, value=None):
        """ Constructor for object """
        #self.guid_id = 0
        self.component_id = component_id
        self.value = value

    def __repr__(self):
        return "Guid object %s" % self.guid_id

class Keyword(db.Model):

    # sqlalchemy metadata
    __tablename__ = 'keywords'
    keyword_id = Column(Integer, primary_key=True, unique=True, nullable=False)
    component_id = Column(Integer, ForeignKey('components.component_id'), nullable=False)
    priority = Column(Integer, default=0)
    value = Column(Text, nullable=False)

    # link back to parent
    md = relationship("Component", back_populates="keywords")

    def __init__(self, value, priority=0):
        """ Constructor for object """
        self.value = value
        self.priority = priority

def _is_keyword_valid(value):
    if not len(value):
        return False
    if value.find('.') != -1:
        return False
    if value in ['a',
                 'bios',
                 'company',
                 'corporation',
                 'development',
                 'device',
                 'firmware',
                 'for',
                 'limited',
                 'system',
                 'the',
                 'update']:
        return False
    return True

def _sanitize_keyword(value):
    for rpl in ['(', ')', '[', ']', '*', '?']:
        value = value.replace(rpl, '')
    return value.strip().lower()

def _split_search_string(value):
    for delim in ['/', ',']:
        value = value.replace(delim, ' ')
    keywords = []
    for word in value.split(' '):
        keyword = _sanitize_keyword(word)
        if not _is_keyword_valid(keyword):
            continue
        if keyword in keywords:
            continue
        keywords.append(keyword)
    return keywords

class Component(db.Model):

    # sqlalchemy metadata
    __tablename__ = 'components'
    component_id = Column(Integer, primary_key=True, unique=True, nullable=False, index=True)
    firmware_id = Column(Integer, ForeignKey('firmware.firmware_id'), nullable=False, index=True)
    checksum_contents = Column(String(40), nullable=False)
    appstream_id = Column(Text, nullable=False)
    name = Column(Text, default=None)
    summary = Column(Text, default=None)
    description = Column(Text, default=None)
    release_description = Column(Text, default=None)
    url_homepage = Column(Text, default=None)
    metadata_license = Column(Text, default=None)
    project_license = Column(Text, default=None)
    developer_name = Column(Text, default=None)
    filename_contents = Column(Text, nullable=False)
    release_timestamp = Column(Integer, default=0)
    version = Column(Text, nullable=False)
    release_installed_size = Column(Integer, default=0)
    release_download_size = Column(Integer, default=0)
    release_urgency = Column(Text, default=None)
    screenshot_url = Column(Text, default=None)
    screenshot_caption = Column(Text, default=None)

    # link back to parent
    fw = relationship("Firmware", back_populates="mds", lazy='joined')

    # include all Component objects
    requirements = relationship("Requirement", back_populates="md")
    guids = relationship("Guid", back_populates="md", lazy='joined')
    keywords = relationship("Keyword", back_populates="md")

    def __init__(self):
        """ Constructor for object """
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

    def add_keywords_from_string(self, value, priority=0):
        existing_keywords = {}
        for kw in self.keywords:
            existing_keywords[kw.value] = kw
        for keyword in _split_search_string(value):
            if keyword in existing_keywords:
                continue
            self.keywords.append(Keyword(keyword, priority))

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
        return "Component object %s" % self.appstream_id

class Remote(db.Model):

    # sqlalchemy metadata
    __tablename__ = 'remotes'
    remote_id = Column(Integer, primary_key=True, unique=True, nullable=False)
    name = Column(Text, nullable=False)
    is_public = Column(Boolean, default=False)

    def __repr__(self):
        return "Remote object %s [%s]" % (self.remote_id, self.name)

class FirmwareEvent(db.Model):

    # sqlalchemy metadata
    __tablename__ = 'firmware_events'
    firmware_event_id = Column(Integer, primary_key=True, unique=True, nullable=False)
    firmware_id = Column(Integer, ForeignKey('firmware.firmware_id'), nullable=False)
    user_id = Column(Integer, ForeignKey('users.user_id'), nullable=False)
    timestamp = Column(DateTime, nullable=False, default=datetime.datetime.utcnow)
    remote_id = Column(Integer, ForeignKey('remotes.remote_id'), nullable=False)

    # link back to parent
    fw = relationship("Firmware", back_populates="events")

    # link using foreign keys
    user = relationship('User', foreign_keys=[user_id])
    remote = relationship('Remote', foreign_keys=[remote_id], lazy='joined')

    def __init__(self, remote_id=None, user_id=0, timestamp=None):
        """ Constructor for object """
        self.remote_id = remote_id
        self.user_id = user_id
        self.timestamp = timestamp

    def __repr__(self):
        return "FirmwareEvent object %s" % self.firmware_event_id

class Firmware(db.Model):

    # sqlalchemy metadata
    __tablename__ = 'firmware'
    firmware_id = Column(Integer, primary_key=True, unique=True, nullable=False, index=True)
    vendor_id = Column(Integer, ForeignKey('vendors.vendor_id'), nullable=False)
    addr = Column(String(40), nullable=False)
    timestamp = Column(DateTime, nullable=False, default=datetime.datetime.utcnow)
    filename = Column(Text, nullable=False)
    download_cnt = Column(Integer, default=0)
    checksum_upload = Column(String(40), nullable=False, index=True)
    version_display = Column(Text, nullable=True, default=None)
    remote_id = Column(Integer, ForeignKey('remotes.remote_id'), nullable=False)
    checksum_signed = Column(String(40), nullable=False)
    user_id = Column(Integer, ForeignKey('users.user_id'), nullable=False)
    inhibit_download = Column(Boolean, default=False)

    # include all Component objects
    mds = relationship("Component", back_populates="fw", lazy='joined')
    events = relationship("FirmwareEvent", back_populates="fw")
    reports = relationship("Report", back_populates="fw")
    clients = relationship("Client", back_populates="fw")

    # link using foreign keys
    vendor = relationship('Vendor', foreign_keys=[vendor_id])
    user = relationship('User', foreign_keys=[user_id])
    remote = relationship('Remote', foreign_keys=[remote_id], lazy='joined')

    @property
    def target_duration(self):
        if not self.events:
            return 0
        return datetime.datetime.utcnow() - self.events[-1].timestamp

    def __init__(self):
        """ Constructor for object """
        self.addr = None
        self.timestamp = None
        self.filename = None        # filename of the original .cab file
        self.checksum_upload = None # SHA1 of the original .cab file
        self.version_display = None # from the firmware.inf file
        self.download_cnt = 0       # generated from the client database
        self.checksum_signed = None # SHA1 of the signed .cab
        self.user_id = None         # user_id of the uploader
        self.mds = []

    def __repr__(self):
        return "Firmware object %s" % self.checksum_upload

class Client(db.Model):

    # sqlalchemy metadata
    __tablename__ = 'clients'
    id = Column(Integer, primary_key=True, nullable=False, unique=True)
    timestamp = Column(DateTime, nullable=False, default=datetime.datetime.utcnow, index=True)
    addr = Column(String(40), nullable=False)
    firmware_id = Column(Integer, ForeignKey('firmware.firmware_id'), nullable=False, index=True)
    user_agent = Column(Text, default=None)

    # link using foreign keys
    fw = relationship('Firmware', foreign_keys=[firmware_id])

    def __init__(self, addr=None, firmware_id=None, user_agent=None, timestamp=None):
        """ Constructor for object """
        self.timestamp = timestamp
        self.addr = addr
        self.firmware_id = firmware_id
        self.user_agent = user_agent

    def __repr__(self):
        return "Client object %s" % self.id

class Condition(db.Model):

    # sqlalchemy metadata
    __tablename__ = 'conditions'
    condition_id = Column(Integer, primary_key=True, nullable=False, unique=True)
    issue_id = Column(Integer, ForeignKey('issues.issue_id'), nullable=False)
    key = Column(Text, nullable=False)
    value = Column(Text, nullable=False)
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

class Issue(db.Model):

    # sqlalchemy metadata
    __tablename__ = 'issues'
    issue_id = Column(Integer, primary_key=True, nullable=False, unique=True)
    priority = Column(Integer, default=0)
    enabled = Column(Boolean, default=False)
    vendor_id = Column(Integer, ForeignKey('vendors.vendor_id'), nullable=False)
    url = Column(Text, default='')
    name = Column(Text, default=None)
    description = Column(Text, default='')
    conditions = relationship("Condition", back_populates="issue")

    # link using foreign keys
    vendor = relationship('Vendor', foreign_keys=[vendor_id])

    def __init__(self, url=None, name=None, description=None, enabled=False, vendor_id=None, priority=0):
        """ Constructor for object """
        self.url = url
        self.name = name
        self.enabled = enabled
        self.priority = priority
        self.description = description
        self.enabled = enabled
        self.vendor_id = vendor_id
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

class ReportAttribute(db.Model):
    __tablename__ = 'report_attributes'
    report_attribute_id = Column(Integer, primary_key=True, nullable=False, unique=True)
    report_id = Column(Integer, ForeignKey('reports.report_id'), nullable=False)
    key = Column(Text, nullable=False)
    value = Column(Text, default=None)

    # link back to parent
    report = relationship("Report", back_populates="attributes")

    def __init__(self, report_id=0, key=None, value=None):
        """ Constructor for object """
        self.report_id = report_id
        self.key = key
        self.value = value

    def __repr__(self):
        return "ReportAttribute object %s=%s" % (self.key, self.value)

class Report(db.Model):

    # sqlalchemy metadata
    __tablename__ = 'reports'
    report_id = Column(Integer, primary_key=True, nullable=False, unique=True)
    timestamp = Column(DateTime, nullable=False, default=datetime.datetime.utcnow)
    state = Column(Integer, default=0)
    machine_id = Column(String(64), nullable=False)
    firmware_id = Column(Integer, ForeignKey('firmware.firmware_id'), nullable=False, index=True)
    checksum = Column(String(64), nullable=False) #fixme remove?
    issue_id = Column(Integer, default=0)

    # link using foreign keys
    fw = relationship('Firmware', foreign_keys=[firmware_id])
    attributes = relationship("ReportAttribute", back_populates="report")

    def __init__(self, firmware_id, machine_id=None, state=0, checksum=None, issue_id=0):
        """ Constructor for object """
        self.timestamp = None
        self.state = state
        self.machine_id = machine_id
        self.firmware_id = firmware_id
        self.issue_id = issue_id
        self.checksum = checksum

    def to_flat_dict(self):
        data = {}
        if self.state == 1:
            data['UpdateState'] = 'pending'
        elif self.state == 2:
            data['UpdateState'] = 'success'
        elif self.state == 3:
            data['UpdateState'] = 'failed'
        elif self.state == 4:
            data['UpdateState'] = 'needs-reboot'
        else:
            data['UpdateState'] = 'unknown'
        if self.machine_id:
            data['MachineId'] = self.machine_id
        if self.firmware_id:
            data['FirmwareId'] = self.firmware_id
        for attr in self.attributes:
            data[attr.key] = attr.value
        return data

    def to_kvs(self):
        flat_dict = self.to_flat_dict()
        kv_array = []
        for key in flat_dict:
            kv_array.append('%s=%s' % (key, flat_dict[key]))
        return ', '.join(sorted(kv_array))

    def __repr__(self):
        return "Report object %s" % self.report_id

class Setting(db.Model):

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

class Analytic(db.Model):

    # sqlalchemy metadata
    __tablename__ = 'analytics'
    datestr = Column(Integer, primary_key=True, unique=True, default=0, index=True)
    cnt = Column(Integer, default=1)

    def __init__(self, datestr=0):
        """ Constructor for object """
        self.cnt = 1
        self.datestr = datestr

    def __repr__(self):
        return "Analytic object %s" % self.datestr

class Useragent(db.Model):

    # sqlalchemy metadata
    __tablename__ = 'useragents'
    useragent_id = Column(Integer, primary_key=True, nullable=False, unique=True)
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


class SearchEvent(db.Model):

    # sqlalchemy metadata
    __tablename__ = 'search_events'
    search_event_id = Column(Integer, primary_key=True, unique=True, nullable=False)
    timestamp = Column(DateTime, nullable=False, default=datetime.datetime.utcnow)
    addr = Column(String(40), nullable=False)
    value = Column(Text, nullable=False)
    count = Column(Integer, default=0)
    method = Column(Text, default=None)

    def __init__(self, value, addr=None, timestamp=None, count=0, method=None):
        """ Constructor for object """
        self.value = value
        self.addr = addr
        self.timestamp = timestamp
        self.count = count
        self.method = method

    def __repr__(self):
        return "SearchEvent object %s" % self.search_event_id
