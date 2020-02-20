#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2015-2018 Richard Hughes <richard@hughsie.com>
#
# SPDX-License-Identifier: GPL-2.0+
#
# pylint: disable=too-few-public-methods,too-many-instance-attributes
# pylint: disable=too-many-arguments,too-many-lines,protected-access
# pylint: wrong-import-position,too-many-public-methods

import os
import datetime
import fnmatch
import functools
import zlib
import re
import math
import hashlib
import collections

from enum import IntEnum

import onetimepass

from flask import g, url_for
from werkzeug.security import generate_password_hash, check_password_hash

from sqlalchemy import Column, Integer, Float, String, Text, Boolean, DateTime, ForeignKey, Index
from sqlalchemy.ext.associationproxy import association_proxy
from sqlalchemy.orm import relationship

from cabarchive import CabArchive
from pkgversion import vercmp

from lvfs import db

from lvfs.dbutils import _execute_count_star
from lvfs.hash import _qa_hash, _password_hash
from lvfs.util import _generate_password, _xml_from_markdown, _get_update_description_problems
from lvfs.util import _get_absolute_path, _get_shard_path, _validate_guid

class Agreement(db.Model):

    __tablename__ = 'agreements'

    agreement_id = Column(Integer, primary_key=True)
    created = Column(DateTime, nullable=False, default=datetime.datetime.utcnow)
    version = Column(Integer, nullable=False)
    text = Column(Text, default=None)

class UserAction(db.Model):

    __tablename__ = 'user_actions'

    user_action_id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.user_id'), nullable=False, index=True)
    ctime = Column(DateTime, nullable=False, default=datetime.datetime.utcnow)
    value = Column(Text, default=None)

    user = relationship('User', foreign_keys=[user_id], back_populates='actions')

    def __repr__(self):
        return "<UserAction {}>".format(self.value)

class User(db.Model):

    __tablename__ = 'users'
    __table_args__ = (Index('idx_users_username_password', 'username', 'password'),
                     )

    user_id = Column(Integer, primary_key=True)
    username = Column(String(80), nullable=False, index=True)
    password_hash = Column('password', String(128), default=None)
    password_ts = Column(DateTime, default=None)
    password_recovery = Column(String(40), default=None)
    password_recovery_ts = Column(DateTime, default=None)
    otp_secret = Column(String(16))
    display_name = Column(Text, default=None)
    vendor_id = Column(Integer, ForeignKey('vendors.vendor_id'), nullable=False, index=True)
    auth_type = Column(Text, default='disabled')
    auth_warning = Column(Text, default=None)
    is_otp_enabled = Column(Boolean, default=False)
    is_otp_working = Column(Boolean, default=False)
    agreement_id = Column(Integer, ForeignKey('agreements.agreement_id'))
    ctime = Column(DateTime, nullable=False, default=datetime.datetime.utcnow)
    mtime = Column(DateTime, nullable=False, default=datetime.datetime.utcnow)
    atime = Column(DateTime, default=None)
    dtime = Column(DateTime, default=None)
    human_user_id = Column(Integer, ForeignKey('users.user_id'), nullable=True)

    vendor = relationship('Vendor', foreign_keys=[vendor_id])
    agreement = relationship('Agreement', foreign_keys=[agreement_id])
    human_user = relationship('User', remote_side=[user_id])

    fws = relationship('Firmware',
                       order_by="desc(Firmware.timestamp)",
                       primaryjoin='Firmware.user_id==User.user_id')
    events = relationship("Event",
                          order_by="desc(Event.timestamp)",
                          lazy='dynamic',
                          cascade='all,delete-orphan')
    queries = relationship("YaraQuery",
                           order_by="desc(YaraQuery.ctime)",
                           cascade='all,delete-orphan')
    certificates = relationship("Certificate",
                                order_by="desc(Certificate.ctime)",
                                cascade='all,delete-orphan')
    actions = relationship("UserAction",
                           lazy='joined',
                           cascade='all,delete-orphan')

    def get_action(self, value):
        for action in self.actions:
            if action.value == value:
                return action
        return None

    @property
    def password(self):
        raise AttributeError('password is not a readable attribute')

    @password.setter
    def password(self, password):
        password_hash = generate_password_hash(password)
        if password_hash != self.password_hash:
            self.password_ts = datetime.datetime.utcnow()
        self.password_hash = password_hash

    def verify_password(self, password):
        # never set, or disabled
        if not self.password_hash:
            return False
        # on success, upgrade the old hashing function to the new secure one
        if len(self.password_hash) == 40:
            if self.password_hash != _password_hash(password):
                return False
            self.password = password
            return True
        return check_password_hash(self.password_hash, password)

    def get_totp_uri(self):
        return 'otpauth://totp/LVFS:{0}?secret={1}&issuer=LVFS' \
            .format(self.username, self.otp_secret)

    @property
    def needs_2fa(self):

        # already done
        if self.is_otp_enabled:
            return False

        # not applicable
        if self.auth_type != 'local':
            return False

        # created in the last 1h...
        if (datetime.datetime.now() - self.ctime.replace(tzinfo=None)).total_seconds() > 60 * 60:
            return False

        # of required userclass
        return self.check_acl('@admin') or self.check_acl('@vendor-manager')

    def verify_totp(self, token):
        return onetimepass.valid_totp(token, self.otp_secret)

    def check_acl(self, action=None):

        # disabled users can do nothing
        if self.auth_type == 'disabled':
            return False

        # decide based on the action
        if action in ['@qa', '@analyst', '@vendor-manager', '@researcher',
                      '@approved-public', '@robot', '@admin', '@partner']:
            return self.get_action(action[1:])
        if action == '@view-profile':
            return self.auth_type == 'local'
        if action == '@view-analytics':
            if self.check_acl('@qa') or self.check_acl('@analyst'):
                return True
            return False
        if action == '@manage-password':
            if self.auth_type == 'local':
                return True
            return False
        if action == '@yara-query':
            return self.check_acl('@admin') or self.check_acl('@researcher')
        if action == '@add-action-researcher':
            if not self.vendor.check_acl('@manage-users'):
                return False
            return self.check_acl('@admin') or self.check_acl('@researcher')
        if action == '@add-action-vendor-manager':
            if not self.vendor.check_acl('@manage-users'):
                return False
            return self.check_acl('@admin') or self.check_acl('@vendor-manager')
        if action == '@add-action-partner':
            return self.check_acl('@admin')
        if action == '@add-action-approved-public':
            if not self.vendor.check_acl('@manage-users'):
                return False
            return self.check_acl('@admin') or self.check_acl('@approved-public')
        if action == '@add-action-analyst':
            if not self.vendor.check_acl('@manage-users'):
                return False
            return self.check_acl('@admin') or self.check_acl('@analyst')
        if action == '@add-action-qa':
            if not self.vendor.check_acl('@manage-users'):
                return False
            return self.check_acl('@admin') or self.check_acl('@qa')
        if action == '@add-action-admin':
            if not self.vendor.check_acl('@manage-users'):
                return False
            return self.check_acl('@admin')
        if action == '@add-action-robot':
            return self.vendor.check_acl('@manage-users')
        if action in ('@view-eventlog', '@view-issues'):
            return self.check_acl('@qa')
        raise NotImplementedError('unknown security check type {}: {}'.format(action, self))

    def generate_password_recovery(self):
        if self.check_acl('@robot'):
            raise RuntimeError('account is a robot')
        if self.auth_type == 'disabled':
            raise RuntimeError('account is locked')
        if self.auth_type == 'local+locked':
            raise RuntimeError('account is locked')
        if self.auth_type == 'oauth':
            raise RuntimeError('account set to OAuth only')
        self.mtime = datetime.datetime.utcnow()
        self.password_recovery = _password_hash(_generate_password())
        self.password_recovery_ts = datetime.datetime.utcnow()

    @property
    def is_authenticated(self):
        return True

    @property
    def email_address(self):
        if self.human_user:
            return self.human_user.username
        return self.username

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

class YaraQueryResult(db.Model):

    __tablename__ = 'yara_query_result'

    yara_query_result_id = Column(Integer, primary_key=True)
    yara_query_id = Column(Integer, ForeignKey('yara_query.yara_query_id'), nullable=False)
    component_shard_id = Column(Integer, ForeignKey('component_shards.component_shard_id'), nullable=True)
    component_id = Column(Integer, ForeignKey('components.component_id'), nullable=False)
    result = Column(Text, default=None)

    query = relationship('YaraQuery', foreign_keys=[yara_query_id])
    shard = relationship('ComponentShard', foreign_keys=[component_shard_id])
    md = relationship('Component', lazy='joined', foreign_keys=[component_id])

    def __repr__(self):
        return "<YaraQueryResult {}>".format(self.yara_query_result_id)

class YaraQuery(db.Model):

    __tablename__ = 'yara_query'

    yara_query_id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.user_id'), nullable=False, index=True)
    value = Column(Text, default=None)
    error = Column(Text, default=None)
    found = Column(Integer, default=0)
    total = Column(Integer, default=0)
    ctime = Column(DateTime, nullable=False, default=datetime.datetime.utcnow)
    started_ts = Column(DateTime, default=None)
    ended_ts = Column(DateTime, default=None)

    user = relationship('User', foreign_keys=[user_id])
    results = relationship("YaraQueryResult", lazy='joined', cascade='all,delete-orphan')

    @property
    def color(self):
        if self.found and self.total:
            return 'warning'
        if self.total:
            return 'success'
        return 'info'

    @property
    def title(self):
        for line in  self.value.replace('{', '\n').split('\n'):
            if line.startswith('rule '):
                return line[5:]
        return None

    @property
    @functools.lru_cache()
    def mds(self):
        mds = {}
        for result in self.results:
            key = '{} {}'.format(result.md.fw.vendor.display_name, result.md.name)
            if key not in mds:
                mds[key] = result.md
        return mds

    def check_acl(self, action, user=None):

        # fall back
        if not user:
            user = g.user
        if user.check_acl('@admin'):
            return True

        # depends on the action requested
        if action == '@modify':
            if user.user_id == self.user_id:
                return True
            return False
        if action == '@delete':
            if user.user_id == self.user_id:
                return True
            return False
        if action == '@retry':
            if user.user_id == self.user_id:
                return True
            return False
        if action == '@show':
            if user.user_id == self.user_id:
                return True
            return False
        raise NotImplementedError('unknown security check action: %s:%s' % (self, action))

    def __repr__(self):
        return "<YaraQuery {}>".format(self.yara_query_id)

class Restriction(db.Model):

    __tablename__ = 'restrictions'

    restriction_id = Column(Integer, primary_key=True)
    vendor_id = Column(Integer, ForeignKey('vendors.vendor_id'), nullable=False, index=True)
    value = Column(Text, nullable=False)

    vendor = relationship("Vendor", back_populates="restrictions")

    def __repr__(self):
        return "Restriction object %s" % self.restriction_id

class Namespace(db.Model):

    __tablename__ = 'namespaces'

    namespace_id = Column(Integer, primary_key=True)
    vendor_id = Column(Integer, ForeignKey('vendors.vendor_id'), nullable=False, index=True)
    value = Column(Text, nullable=False)
    ctime = Column(DateTime, nullable=False, default=datetime.datetime.utcnow)
    user_id = Column(Integer, ForeignKey('users.user_id'), nullable=False)

    vendor = relationship("Vendor", back_populates="namespaces")
    user = relationship('User', foreign_keys=[user_id])

    @property
    def is_valid(self):
        if self.value.endswith('.'):
            return False
        if self.value.find('.') == -1:
            return False
        return True

    def __repr__(self):
        return '<Namespace {}>'.format(self.value)

class AffiliationAction(db.Model):

    __tablename__ = 'affiliation_actions'

    affiliation_action_id = Column(Integer, primary_key=True)
    affiliation_id = Column(Integer, ForeignKey('affiliations.affiliation_id'), nullable=False, index=True)
    ctime = Column(DateTime, nullable=False, default=datetime.datetime.utcnow)
    user_id = Column(Integer, ForeignKey('users.user_id'), nullable=False)
    action = Column(Text, default=None)

    user = relationship('User', foreign_keys=[user_id])
    affiliation = relationship('Affiliation', foreign_keys=[affiliation_id])

    def __repr__(self):
        return "<AffiliationAction {}>".format(self.action)

class Affiliation(db.Model):

    __tablename__ = 'affiliations'

    affiliation_id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime, nullable=False, default=datetime.datetime.utcnow)
    vendor_id = Column(Integer, ForeignKey('vendors.vendor_id'), nullable=False, index=True)
    vendor_id_odm = Column(Integer, ForeignKey('vendors.vendor_id'), nullable=False, index=True)

    vendor = relationship("Vendor", foreign_keys=[vendor_id], back_populates="affiliations")
    vendor_odm = relationship("Vendor", foreign_keys=[vendor_id_odm])
    actions = relationship("AffiliationAction", cascade='all,delete-orphan')

    def get_action(self, action):
        for act in self.actions:
            if action == act.action:
                return act
        return None

    def __repr__(self):
        return "Affiliation object %s" % self.affiliation_id

class Vendor(db.Model):

    __tablename__ = 'vendors'

    vendor_id = Column(Integer, primary_key=True)
    group_id = Column(String(80), nullable=False, index=True)
    display_name = Column(Text, default=None)
    internal_team = Column(Text, default=None)
    plugins = Column(Text, default=None)
    description = Column(Text, default=None)
    quote_text = Column(Text, default=None)
    quote_author = Column(Text, default=None)
    consulting_text = Column(Text, default=None)
    consulting_link = Column(Text, default=None)
    visible = Column(Boolean, default=False)
    visible_for_search = Column(Boolean, default=False)
    visible_on_landing = Column(Boolean, default=False)
    is_embargo_default = Column(Boolean, default=False)
    comments = Column(Text, default=None)
    icon = Column(Text, default=None)
    keywords = Column(Text, default=None)
    oauth_unknown_user = Column(Text, default=None)
    oauth_domain_glob = Column(Text, default=None)
    remote_id = Column(Integer, ForeignKey('remotes.remote_id'), nullable=False)
    username_glob = Column(Text, default=None)
    verfmt_id = Column(Integer, ForeignKey('verfmts.verfmt_id'))
    url = Column(Text, default=None)
    banned_country_codes = Column(Text, default=None) # ISO 3166, delimiter ','
    do_not_track = Column(Boolean, default=False)

    users = relationship("User",
                         back_populates="vendor",
                         cascade='all,delete-orphan')
    restrictions = relationship("Restriction",
                                back_populates="vendor",
                                cascade='all,delete-orphan')
    namespaces = relationship("Namespace",
                              back_populates="vendor",
                              cascade='all,delete-orphan')
    affiliations = relationship("Affiliation",
                                foreign_keys=[Affiliation.vendor_id],
                                back_populates="vendor",
                                cascade='all,delete-orphan')
    affiliations_for = relationship("Affiliation",
                                    foreign_keys=[Affiliation.vendor_id_odm],
                                    back_populates="vendor")
    fws = relationship("Firmware",
                       cascade='all,delete-orphan')
    mdrefs = relationship('ComponentRef',
                          foreign_keys='[ComponentRef.vendor_id_partner]',
                          cascade='all,delete-orphan',
                          back_populates='vendor_partner')
    events = relationship("Event",
                          order_by="desc(Event.timestamp)",
                          lazy='dynamic',
                          cascade='all,delete-orphan')

    verfmt = relationship('Verfmt', foreign_keys=[verfmt_id])
    remote = relationship('Remote',
                          foreign_keys=[remote_id],
                          single_parent=True,
                          cascade='all,delete-orphan')

    @property
    @functools.lru_cache()
    def fws_stable_recent(self):
        now = datetime.datetime.utcnow() - datetime.timedelta(weeks=25)
        return _execute_count_star(db.session.query(Firmware.firmware_id).\
                    join(Firmware.remote).\
                    filter(Remote.name == 'stable',
                           Firmware.vendor_id == self.vendor_id,
                           Firmware.timestamp > now))

    @property
    @functools.lru_cache()
    def fws_stable(self):
        return _execute_count_star(db.session.query(Firmware.firmware_id).\
                    join(Firmware.remote).\
                    filter(Firmware.vendor_id == self.vendor_id,
                           Remote.name == 'stable'))

    @property
    @functools.lru_cache()
    def is_odm(self):
        return db.session.query(Affiliation.affiliation_id).\
                    filter(Affiliation.vendor_id_odm == self.vendor_id).\
                    first() is not None

    @property
    @functools.lru_cache()
    def protocols(self):
        return db.session.query(Protocol).join(Component).\
                    join(Firmware).filter(Firmware.vendor_id == self.vendor_id).\
                    join(Remote).filter(Remote.name == 'stable').\
                    order_by(Protocol.name.asc()).\
                    all()

    @property
    def is_account_holder(self):
        return self.users

    @property
    def is_unrestricted(self):
        for res in self.restrictions:
            if res.value == '*':
                return True
        return False

    @property
    def display_name_with_team(self):
        if self.internal_team:
            return '{} ({})'.format(self.display_name, self.internal_team)
        return self.display_name

    @property
    def ctime(self):
        val = None
        for user in self.users:
            if not user.ctime:
                continue
            if not val or user.ctime < val:
                val = user.ctime
        return val

    @property
    def mtime(self):
        val = None
        for user in self.users:
            if not user.mtime:
                continue
            if not val or user.mtime > val:
                val = user.mtime
        return val

    @property
    def atime(self):
        val = None
        for user in self.users:
            if not user.atime:
                continue
            if not val or user.atime > val:
                val = user.atime
        return val

    def is_affiliate_for(self, vendor_id):
        for rel in self.affiliations_for:
            if rel.vendor_id == vendor_id:
                return True
        return False

    def is_affiliate(self, vendor_id_odm):
        for rel in self.affiliations:
            if rel.vendor_id_odm == vendor_id_odm:
                return True
        return False

    def check_acl(self, action, user=None):

        # fall back
        if not user:
            user = g.user
        if user.check_acl('@admin'):
            return True

        # depends on the action requested
        if action == '@upload':
            # all members of a group can upload to that group
            if user.vendor_id == self.vendor_id:
                return True
            # allow vendor affiliates too
            if self.is_affiliate(user.vendor_id):
                return True
            return False
        if action == '@view-metadata':
            # all members of a group can generate the metadata file
            if user.vendor_id == self.vendor_id:
                return True
            return False
        if action == '@manage-users':
            if user.vendor_id != self.vendor_id:
                return False
            # manager user can modify any users in his group
            if user.check_acl('@vendor-manager'):
                return True
            return False
        if action == '@modify-oauth':
            return False
        if action == '@view-affiliations':
            if user.vendor_id != self.vendor_id:
                return False
            return user.check_acl('@vendor-manager')
        if action == '@view-restrictions':
            if user.vendor_id != self.vendor_id:
                return False
            return user.check_acl('@vendor-manager')
        if action == '@modify-affiliations':
            return False
        if action == '@modify-affiliation-actions':
            if user.vendor_id != self.vendor_id:
                return False
            return user.check_acl('@vendor-manager')
        if action == '@view-exports':
            if user.vendor_id != self.vendor_id:
                return False
            return user.check_acl('@qa') or user.check_acl('@vendor-manager')
        if action == '@modify-exports':
            return user.check_acl('@vendor-manager')
        raise NotImplementedError('unknown security check action: %s:%s' % (self, action))

    def __hash__(self):
        return self.vendor_id

    def __lt__(self, other):
        return self.vendor_id < other.vendor_id

    def __eq__(self, other):
        return self.vendor_id == other.vendor_id

    def __repr__(self):
        return "Vendor object %s" % self.group_id

class Event(db.Model):

    __tablename__ = 'event_log'

    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime, nullable=False, default=datetime.datetime.utcnow)
    user_id = Column(Integer, ForeignKey('users.user_id'), nullable=False, index=True)
    vendor_id = Column(Integer, ForeignKey('vendors.vendor_id'), nullable=False, index=True)
    address = Column('addr', String(40), nullable=False)
    message = Column(Text, default=None)
    is_important = Column(Boolean, default=False)
    request = Column(Text, default=None)

    vendor = relationship('Vendor', foreign_keys=[vendor_id])
    user = relationship('User', foreign_keys=[user_id])

    def __repr__(self):
        return "Event object %s" % self.message

class Certificate(db.Model):

    __tablename__ = 'certificates'

    certificate_id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.user_id'), nullable=False, index=True)
    ctime = Column(DateTime, nullable=False, default=datetime.datetime.utcnow)
    serial = Column(String(40), nullable=False)
    text = Column(Text, default=None)

    user = relationship('User', foreign_keys=[user_id])

    def check_acl(self, action, user=None):

        # fall back
        if not user:
            user = g.user
        if user.check_acl('@admin'):
            return True

        # depends on the action requested
        if action == '@delete':
            if self.user_id == user.user_id:
                return True
            return False
        raise NotImplementedError('unknown security check action: %s:%s' % (self, action))

    def __repr__(self):
        return "Certificate object %s" % self.serial

class Requirement(db.Model):

    __tablename__ = 'requirements'

    requirement_id = Column(Integer, primary_key=True)
    component_id = Column(Integer, ForeignKey('components.component_id'), nullable=False, index=True)
    kind = Column(Text, nullable=False)
    value = Column(Text, default=None)
    compare = Column(Text, default=None)
    version = Column(Text, default=None)
    depth = Column(Integer, default=None)

    md = relationship("Component", back_populates="requirements")

    def __repr__(self):
        return "Requirement object %s/%s/%s/%s" % (self.kind, self.value, self.compare, self.version)

class Guid(db.Model):

    __tablename__ = 'guids'
    guid_id = Column(Integer, primary_key=True)
    component_id = Column(Integer, ForeignKey('components.component_id'), nullable=False, index=True)
    value = Column(Text, nullable=False)

    md = relationship("Component", back_populates="guids")

    def __repr__(self):
        return "Guid object %s" % self.guid_id

class Keyword(db.Model):

    __tablename__ = 'keywords'

    keyword_id = Column(Integer, primary_key=True)
    component_id = Column(Integer, ForeignKey('components.component_id'), nullable=False, index=True)
    priority = Column(Integer, default=0)
    value = Column(Text, nullable=False)

    md = relationship("Component", back_populates="keywords")

    def __repr__(self):
        return "Keyword object %s" % self.value

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

class Checksum(db.Model):

    __tablename__ = 'checksums'

    checksum_id = Column(Integer, primary_key=True)
    component_id = Column(Integer, ForeignKey('components.component_id'), nullable=False, index=True)
    kind = Column(Text, nullable=False, default=None)
    value = Column(Text, nullable=False, default=None)

    md = relationship("Component")

    def __repr__(self):
        return "Checksum object %s(%s)" % (self.kind, self.value)

class TestAttribute(db.Model):
    __tablename__ = 'test_attributes'

    test_attribute_id = Column(Integer, primary_key=True)
    test_id = Column(Integer, ForeignKey('tests.test_id'), nullable=False, index=True)
    title = Column(Text, nullable=False)
    message = Column(Text, default=None)
    success = Column(Boolean, default=False)

    test = relationship("Test", back_populates="attributes")

    def __repr__(self):
        return "TestAttribute object %s=%s" % (self.title, self.message)

class Test(db.Model):

    __tablename__ = 'tests'

    test_id = Column(Integer, primary_key=True)
    firmware_id = Column(Integer, ForeignKey('firmware.firmware_id'), nullable=False, index=True)
    plugin_id = Column(Text, default=None)
    waivable = Column(Boolean, default=False)
    scheduled_ts = Column(DateTime, nullable=False, default=datetime.datetime.utcnow)
    started_ts = Column(DateTime, default=None)
    ended_ts = Column(DateTime, default=None)
    waived_ts = Column(DateTime, default=None)
    waived_user_id = Column(Integer, ForeignKey('users.user_id'), nullable=True)
    max_age = Column(Integer, default=0)

    waived_user = relationship('User', foreign_keys=[waived_user_id])
    attributes = relationship("TestAttribute",
                              lazy='joined',
                              back_populates="test",
                              cascade='all,delete-orphan')

    fw = relationship("Firmware", back_populates="tests")

    def add_pass(self, title, message=None):
        self.attributes.append(TestAttribute(title=title, message=message, success=True))

    def add_fail(self, title, message=None):
        self.attributes.append(TestAttribute(title=title, message=message, success=False))

    def waive(self):
        self.waived_ts = datetime.datetime.utcnow()
        self.waived_user_id = g.user.user_id

    def retry(self):
        self.scheduled_ts = datetime.datetime.utcnow()
        self.started_ts = None
        self.ended_ts = None
        self.waived_ts = None
        for attr in self.attributes:
            db.session.delete(attr)

    def check_acl(self, action, user=None):

        # fall back
        if not user:
            user = g.user
        if user.check_acl('@admin'):
            return True

        # depends on the action requested
        if action == '@retry':
            if user.check_acl('@qa') and self.fw._is_permitted_action(action, user):
                return True
            if self.fw._is_owner(user):
                return True
            return False
        if action == '@waive':
            if user.check_acl('@qa') and self.fw._is_permitted_action(action, user):
                return True
            return False
        raise NotImplementedError('unknown security check action: %s:%s' % (self, action))

    @property
    def timestamp(self):
        if self.ended_ts:
            return self.ended_ts
        if self.started_ts:
            return self.started_ts
        return self.scheduled_ts

    @property
    def is_pending(self):
        if not self.started_ts:
            return True
        return False

    @property
    def is_waived(self):
        if self.waived_ts:
            return True
        return False

    @property
    def is_running(self):
        if self.started_ts and not self.ended_ts:
            return True
        return False

    @property
    def color(self):
        if self.success:
            return 'success'
        if self.is_running:
            return 'info'
        if self.is_pending:
            return 'info'
        if self.is_waived:
            return 'warning'
        return 'danger'

    @property
    def success(self):
        if not self.attributes:
            return True
        for attr in self.attributes:
            if not attr.success:
                return False
        return True

    def __repr__(self):
        return "Test object %s(%s)" % (self.plugin_id, self.success)

class Verfmt(db.Model):

    __tablename__ = 'verfmts'

    verfmt_id = Column(Integer, primary_key=True)
    value = Column(Text, nullable=False)        # 'dell-bios'
    name = Column(Text, default=None)           # 'Dell Style'
    example = Column(Text, default=None)        # '12.34.56.78'
    fwupd_version = Column(Text, default=None)  # '1.3.3'
    fallbacks = Column(Text, default=None)      # 'quad,intelme'

    @property
    def sections(self):
        if not self.example:
            return 0
        return len(self.example.split('.'))

    def uint32_to_str(self, v):
        if self.value == 'plain':
            return str(v)
        if self.value == 'quad':
            return '%i.%i.%i.%i' % ((v & 0xff000000) >> 24,
                                    (v & 0x00ff0000) >> 16,
                                    (v & 0x0000ff00) >> 8,
                                    v & 0x000000ff)
        if self.value == 'triplet':
            return '%i.%i.%i' % ((v & 0xff000000) >> 24,
                                 (v & 0x00ff0000) >> 16,
                                 v & 0x0000ffff)
        if self.value == 'pair':
            return '%i.%i' % ((v & 0xffff0000) >> 16, v & 0x0000ffff)
        if self.value == 'intel-me':
            return '%i.%i.%i.%i' % (((v & 0xe0000000) >> 29) + 0x0b,
                                    (v & 0x1f000000) >> 24,
                                    (v & 0x00ff0000) >> 16,
                                    v &  0x0000ffff)
        if self.value == 'intel-me2':
            return '%i.%i.%i.%i' % ((v & 0xf0000000) >> 28,
                                    (v & 0x0f000000) >> 24,
                                    (v & 0x00ff0000) >> 16,
                                    v &  0x0000ffff)
        if self.value == 'surface-legacy':
            return '%i.%i.%i' % ((v >> 22) & 0x3ff,
                                 (v >> 10) & 0xfff,
                                 v & 0x3ff)
        if self.value == 'surface':
            return '%i.%i.%i' % ((v >> 24) & 0xff,
                                 (v >> 8) & 0xffff,
                                 v & 0xff)
        if self.value == 'bcd':
            return '%i.%i' % ((v & 0xf0) >> 4, v & 0x0f)
        if self.value == 'dell-bios':
            return '%i.%i.%i' % ((v & 0x00ff0000) >> 16,
                                 (v & 0x0000ff00) >> 8,
                                 v & 0x000000ff)
        return None

    def __repr__(self):
        return "Verfmt object %s:%s" % (self.category_id, self.value)

class Category(db.Model):

    __tablename__ = 'categories'

    category_id = Column(Integer, primary_key=True)
    value = Column(Text, nullable=False)        # 'X-System'
    name = Column(Text, default=None)           # 'System Update'
    fallbacks = Column(Text, default=None)
    expect_device_checksum = Column(Boolean, default=False)

    def matches(self, values):
        for value in values:
            if self.value == value:
                return True
        if self.fallbacks:
            for value in values:
                if value in self.fallbacks.split(','):
                    return True
        return False

    def __repr__(self):
        return "Category object %s:%s" % (self.category_id, self.value)

class Claim(db.Model):

    __tablename__ = 'claims'

    claim_id = Column(Integer, primary_key=True)
    kind = Column(Text, nullable=False, index=True)
    icon = Column(Text)     # e.g. 'success'
    summary = Column(Text)
    description = Column(Text, default=None)
    url = Column(Text)

    def __lt__(self, other):
        if self.icon != other.icon:
            return self.icon < other.icon
        return self.kind < other.kind

    def __eq__(self, other):
        return self.kind == other.kind

    @property
    def icon_css(self):
        if self.icon in ['danger', 'warning']:
            return ['fas', 'fa-times-circle', 'text-' + self.icon]
        if self.icon == 'info':
            return ['fas', 'fa-info-circle', 'text-' + self.icon]
        if self.icon == 'success':
            return ['fas', 'fa-check-circle', 'text-' + self.icon]
        if self.icon == 'waiting':
            return ['far', 'fa-clock', 'text-info']
        return ['far', 'fa-{}'.format(self.icon)]

    def __repr__(self):
        return 'Claim object {}:{}->{}'.format(self.claim_id, self.kind, self.icon)

class ComponentShardInfo(db.Model):

    __tablename__ = 'component_shard_infos'

    component_shard_info_id = Column(Integer, primary_key=True)
    guid = Column(String(36), default=None, index=True)
    description = Column(Text, default=None)
    cnt = Column(Integer, default=0)
    claim_id = Column(Integer, ForeignKey('claims.claim_id'), nullable=True, index=True)

    shards = relationship("ComponentShard", cascade='all,delete-orphan')
    claim = relationship('Claim')

    def __repr__(self):
        return "ComponentShardInfo object %s" % self.component_shard_info_id

class ComponentShardChecksum(db.Model):

    __tablename__ = 'component_shard_checksums'

    checksum_id = Column(Integer, primary_key=True)
    component_shard_id = Column(Integer, ForeignKey('component_shards.component_shard_id'), nullable=False, index=True)
    kind = Column(Text, nullable=False, default=None)
    value = Column(Text, nullable=False, default=None)

    shard = relationship("ComponentShard")

    def __repr__(self):
        return "ComponentShardChecksum object %s(%s)" % (self.kind, self.value)

class ComponentShardCertificate(db.Model):

    __tablename__ = 'component_shard_certificates'

    component_shard_certificate_id = Column(Integer, primary_key=True)
    component_shard_id = Column(Integer, ForeignKey('component_shards.component_shard_id'), nullable=False, index=True)
    kind = Column(Text, default=None)
    plugin_id = Column(Text, default=None)
    description = Column(Text, default=None)
    serial_number = Column(Text, default=None)
    not_before = Column(DateTime, default=None)
    not_after = Column(DateTime, default=None)

    shard = relationship('ComponentShard', back_populates="certificates")

    @property
    def color(self):
        if self.not_before and self.not_before > self.shard.md.fw.timestamp:
            return 'danger'
        if self.not_after and self.not_after < self.shard.md.fw.timestamp:
            return 'danger'
        return 'success'

    def __repr__(self):
        data = []
        if self.serial_number:
            data.append('serial_number:{}'.format(self.serial_number))
        if self.not_before:
            data.append('not_before:{}'.format(self.not_before))
        if self.not_after:
            data.append('not_after:{}'.format(self.not_after))
        if self.description:
            data.append('desc:{}'.format(self.description))
        return 'ComponentShardCertificate ({})'.format(', '.join(data))

def _calculate_entropy(s):
    probabilities = [n_x / len(s) for x, n_x in collections.Counter(s).items()]
    e_x = [- p_x * math.log(p_x, 2) for p_x in probabilities]
    return sum(e_x)

class ComponentShardClaim(db.Model):

    __tablename__ = 'component_shard_claims'

    component_shard_claim_id = Column(Integer, primary_key=True)
    component_shard_info_id = Column(Integer, ForeignKey('component_shard_infos.component_shard_info_id'))
    checksum = Column(Text, nullable=False, default=None)
    claim_id = Column(Integer, ForeignKey('claims.claim_id'), nullable=True)

    info = relationship('ComponentShardInfo')
    claim = relationship('Claim')

    def __repr__(self):
        return "ComponentShardClaim object {},{} -> {}({})"\
                    .format(self.info.guid, self.checksum, self.kind, self.value)

class ComponentShardAttribute(db.Model):
    __tablename__ = 'component_shard_attributes'

    component_shard_attribute_id = Column(Integer, primary_key=True)
    component_shard_id = Column(Integer, ForeignKey('component_shards.component_shard_id'), nullable=False, index=True)
    key = Column(Text, nullable=False)
    value = Column(Text, default=None)

    component_shard = relationship("ComponentShard", back_populates="attributes")

    def __repr__(self):
        return "ComponentShardAttribute object %s=%s" % (self.key, self.value)

class ComponentShard(db.Model):

    __tablename__ = 'component_shards'

    component_shard_id = Column(Integer, primary_key=True)
    component_id = Column(Integer, ForeignKey('components.component_id'), nullable=False, index=True)
    component_shard_info_id = Column(Integer,
                                     ForeignKey('component_shard_infos.component_shard_info_id'),
                                     default=None)
    plugin_id = Column(Text, default=None)
    guid = Column(String(36), default=None, index=True)
    name = Column(Text, default=None)
    size = Column(Integer, default=0)
    entropy = Column(Float, default=0.0)

    checksums = relationship("ComponentShardChecksum",
                             back_populates="shard",
                             cascade='all,delete-orphan')
    certificates = relationship("ComponentShardCertificate",
                                order_by="desc(ComponentShardCertificate.component_shard_certificate_id)",
                                back_populates='shard',
                                cascade='all,delete-orphan')
    info = relationship('ComponentShardInfo')
    yara_query_results = relationship('YaraQueryResult')

    md = relationship('Component', back_populates="shards")
    attributes = relationship("ComponentShardAttribute",
                              back_populates="component_shard",
                              cascade='all,delete-orphan')

    def get_attr_value(self, key):
        for attr in self.attributes:
            if attr.key == key:
                return attr.value
        return None

    @property
    def description(self):
        if self.info.description:
            return self.info.description
        if self.name.endswith('Pei'):
            return 'The Pre-EFI Initialization phase is invoked early in the boot flow.'
        if self.name.endswith('Dxe'):
            return 'The Driver Execution Environment phase is where most of the system \
                    initialization is performed.'
        return None

    @property
    def blob(self):
        if not hasattr(self, '_blob'):
            # restore from disk if available
            fn = _get_shard_path(self)
            if not os.path.exists(fn):
                return None
            with open(fn, 'rb') as f:
                self._blob = zlib.decompress(f.read())
        return self._blob

    @blob.setter
    def blob(self, value):
        self._blob = value

    @property
    def checksum(self):
        for csum in self.checksums:
            if csum.kind == 'SHA256':
                return csum.value
        return None

    def set_blob(self, value, checksums=None):
        """ Set data blob and add checksum objects """
        self._blob = value
        self.size = len(value)
        self.entropy = _calculate_entropy(value)

        # default fallback
        if not checksums:
            checksums = ['SHA1', 'SHA256']

        # SHA1 is what's used by researchers, but considered broken
        if 'SHA1' in checksums:
            csum = ComponentShardChecksum(value=hashlib.sha1(value).hexdigest(), kind='SHA1')
            self.checksums.append(csum)

        # SHA256 is now the best we have
        if 'SHA256' in checksums:
            csum = ComponentShardChecksum(value=hashlib.sha256(value).hexdigest(), kind='SHA256')
            self.checksums.append(csum)

    def save(self):
        fn = _get_shard_path(self)
        os.makedirs(os.path.dirname(fn), exist_ok=True)
        with open(fn, 'wb') as f:
            f.write(zlib.compress(self._blob))

    def __repr__(self):
        return "ComponentShard object %s" % self.component_shard_id

class ComponentIssue(db.Model):

    __tablename__ = 'component_issues'

    component_issue_id = Column(Integer, primary_key=True)
    component_id = Column(Integer, ForeignKey('components.component_id'), nullable=False, index=True)
    kind = Column(Text, nullable=False)
    value = Column(Text, nullable=False)

    md = relationship("Component", back_populates="issues")

    @property
    def url(self):
        if self.kind == 'cve':
            return 'https://nvd.nist.gov/vuln/detail/{}'.format(self.value)
        if self.kind == 'dell':
            # you have to search for the issue number yourself...
            return 'https://www.dell.com/support/security/en-us/'
        if self.kind == 'lenovo':
            return 'https://support.lenovo.com/us/en/product_security/{}'.format(self.value)
        if self.kind == 'intel':
            return 'https://www.intel.com/content/www/us/en/security-center/advisory/{}'.format(self.value)
        return None

    @property
    def problem(self):
        if self.kind == 'cve':
            parts = self.value.split('-')
            if len(parts) != 3 or parts[0] != 'CVE':
                return Claim(kind='invalid-issue',
                             icon='warning',
                             summary='Invalid component issue',
                             description='Format expected to be CVE-XXXX-XXXXX')
            if not parts[1].isnumeric or int(parts[1]) < 1995:
                return Claim(kind='invalid-issue',
                             icon='warning',
                             summary='Invalid component issue',
                             description='Invalid year in CVE value')
            if not parts[2].isnumeric:
                return Claim(kind='invalid-issue',
                             icon='warning',
                             summary='Invalid component issue',
                             description='Expected integer in CVE token')
            return None
        if self.kind == 'dell':
            parts = self.value.split('-')
            if len(parts) != 3 or parts[0] != 'DSA':
                return Claim(kind='invalid-issue',
                             icon='warning',
                             summary='Invalid component issue',
                             description='Format expected to be DSA-XXXX-XXX')
            if not parts[1].isnumeric or int(parts[1]) < 1995:
                return Claim(kind='invalid-issue',
                             icon='warning',
                             summary='Invalid component issue',
                             description='Invalid year in DSA value')
            if not parts[2].isnumeric:
                return Claim(kind='invalid-issue',
                             icon='warning',
                             summary='Invalid component issue',
                             description='Expected integer in DSA token')
            return None
        if self.kind == 'lenovo':
            parts = self.value.split('-')
            if len(parts) != 2 or parts[0] != 'LEN':
                return Claim(kind='invalid-issue',
                             icon='warning',
                             summary='Invalid component issue',
                             description='Format expected to be LEN-XXXXX')
            if not parts[1].isnumeric:
                return Claim(kind='invalid-issue',
                             icon='warning',
                             summary='Invalid component issue',
                             description='Expected integer in LEN token')
            return None
        if self.kind == 'intel':
            parts = self.value.split('-')
            if len(parts) != 3 or parts[0] != 'INTEL' or parts[1] != 'SA':
                return Claim(kind='invalid-issue',
                             icon='warning',
                             summary='Invalid component issue',
                             description='Format expected to be INTEL-SA-XXXXX')
            if not parts[2].isnumeric:
                return Claim(kind='invalid-issue',
                             icon='warning',
                             summary='Invalid component issue',
                             description='Expected integer in INTEL-SA token')
            return None
        return Claim(kind='invalid-issue',
                     icon='warning',
                     summary='Invalid component kind',
                     description='Issue kind {} not supported'.format(self.kind))

    def __repr__(self):
        return '<ComponentIssue {}>'.format(self.value)

def _is_valid_url(url):
    if not url.startswith('https://') and not url.startswith('http://'):
        return False
    return True

class ComponentClaim(db.Model):

    __tablename__ = 'component_claims'

    component_claim_id = Column(Integer, primary_key=True)
    component_id = Column(Integer, ForeignKey('components.component_id'), nullable=False, index=True)
    claim_id = Column(Integer, ForeignKey('claims.claim_id'), nullable=False, index=True)

    md = relationship('Component', back_populates='component_claims')
    claim = relationship('Claim')

    def __repr__(self):
        return '<ComponentClaim {}>'.format(self.component_claim_id)

class ComponentRef(db.Model):

    __tablename__ = 'component_refs'

    component_ref_id = Column(Integer, primary_key=True)
    component_id = Column(Integer, ForeignKey('components.component_id'), index=True)
    vendor_id = Column(Integer, ForeignKey('vendors.vendor_id'), nullable=False, index=True)
    vendor_id_partner = Column(Integer, ForeignKey('vendors.vendor_id'), nullable=False, index=True)
    protocol_id = Column(Integer, ForeignKey('protocol.protocol_id'))
    appstream_id = Column(Text, default=None)
    version = Column(Text, nullable=False)
    release_tag = Column(Text, default=None)
    date = Column(DateTime, default=None)
    name = Column(Text, nullable=False)
    url = Column(Text, default=None)
    status = Column(Text)

    md = relationship('Component')
    vendor = relationship('Vendor', foreign_keys=[vendor_id])
    vendor_partner = relationship('Vendor', foreign_keys=[vendor_id_partner], back_populates='mdrefs')
    protocol = relationship('Protocol')

    def __lt__(self, other):
        return vercmp(self.version, other.version) < 0

    def __eq__(self, other):
        return vercmp(self.version, other.version) == 0

    @property
    def version_with_tag(self):
        if self.release_tag:
            return '{} ({})'.format(self.release_tag, self.version)
        return self.version

    def __repr__(self):
        return '<ComponentRef {}>'.format(self.version)

class Component(db.Model):

    __tablename__ = 'components'

    component_id = Column(Integer, primary_key=True)
    firmware_id = Column(Integer, ForeignKey('firmware.firmware_id'), nullable=False, index=True)
    protocol_id = Column(Integer, ForeignKey('protocol.protocol_id'))
    category_id = Column(Integer, ForeignKey('categories.category_id'))
    checksum_contents = Column(String(40), nullable=False)
    appstream_id = Column(Text, nullable=False)
    name = Column(Text, default=None)
    name_variant_suffix = Column(Text, default=None)
    summary = Column(Text, default=None)
    description = Column(Text, default=None)            # markdown format
    release_description = Column(Text, default=None)    # markdown format
    details_url = Column(Text, default=None)
    source_url = Column(Text, default=None)
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
    release_tag = Column(Text, default=None)
    screenshot_url = Column(Text, default=None)
    screenshot_caption = Column(Text, default=None)
    inhibit_download = Column(Boolean, default=False)
    verfmt_id = Column(Integer, ForeignKey('verfmts.verfmt_id'))
    priority = Column(Integer, default=0)
    install_duration = Column(Integer, default=0)

    fw = relationship("Firmware", back_populates="mds", lazy='joined')
    requirements = relationship("Requirement",
                                back_populates="md",
                                cascade='all,delete-orphan')
    issues = relationship('ComponentIssue',
                          back_populates='md',
                          cascade='all,delete-orphan')
    component_claims = relationship('ComponentClaim',
                                    back_populates='md',
                                    cascade='all,delete-orphan')
    issue_values = association_proxy('issues', 'value')
    device_checksums = relationship("Checksum",
                                    back_populates="md",
                                    cascade='all,delete-orphan')
    guids = relationship("Guid",
                         back_populates="md",
                         lazy='joined',
                         cascade='all,delete-orphan')
    shards = relationship("ComponentShard",
                          order_by="desc(ComponentShard.component_shard_id)",
                          back_populates='md',
                          cascade='all,delete-orphan')
    keywords = relationship("Keyword",
                            back_populates="md",
                            cascade='all,delete-orphan')
    protocol = relationship('Protocol', foreign_keys=[protocol_id])
    category = relationship('Category', foreign_keys=[category_id])
    verfmt = relationship('Verfmt', foreign_keys=[verfmt_id])

    def __lt__(self, other):
        return vercmp(self.version_display, other.version_display) < 0

    def __eq__(self, other):
        return vercmp(self.version_display, other.version_display) == 0

    @property
    def blob(self):
        if not hasattr(self, '_blob') or not self._blob:
            self._blob = None
            self.fw._ensure_blobs()
        return self._blob

    @blob.setter
    def blob(self, value):
        self._blob = value

    @property
    def names(self):
        if not self.name:
            return None
        return self.name.split('/')

    @property
    def appstream_id_prefix(self):
        sections = self.appstream_id.split('.', maxsplit=4)
        return '.'.join(sections[:2])

    @property
    def certificates(self):
        certs = []
        for shard in self.shards:
            certs.extend(shard.certificates)
        return certs

    @property
    def name_with_category(self):
        name = self.name
        if self.name_variant_suffix:
            name += ' (' + self.name_variant_suffix + ')'
        if self.category:
            if self.category.name:
                name += ' ' + self.category.name
            else:
                name += ' ' + self.category.value
        return name

    @property
    def name_with_vendor(self):
        name = self.fw.vendor.display_name + ' ' + self.name
        if self.name_variant_suffix:
            name += ' (' + self.name_variant_suffix + ')'
        return name

    @property
    def verfmt_with_fallback(self):
        if self.verfmt:
            return self.verfmt
        if self.protocol and self.protocol.verfmt:
            return self.protocol.verfmt
        if self.fw.vendor.verfmt and self.protocol and self.protocol.value == 'org.uefi.capsule':
            return self.fw.vendor.verfmt
        return None

    @property
    def developer_name_display(self):
        if not self.developer_name:
            return None
        tmp = str(self.developer_name)
        for suffix in [' Limited', ' Ltd.', ' Inc.', ' Corp']:
            if tmp.endswith(suffix):
                return tmp[:-len(suffix)]
        return tmp

    @property
    def claims(self):
        return [component_claim.claim for component_claim in self.component_claims]

    @property
    def autoclaims(self):
        claims = []
        if self.protocol:
            if self.protocol.is_signed:
                claims.append(Claim(kind='signed-firmware',
                                    icon='success',
                                    summary='Update is cryptographically signed',
                                    url='https://lvfs.readthedocs.io/en/latest/claims.html#signed-firmware'))
            else:
                claims.append(Claim(kind='no-signed-firmware',
                                    icon='warning',
                                    summary='Update is not cryptographically signed',
                                    url='https://lvfs.readthedocs.io/en/latest/claims.html#signed-firmware'))
            if self.protocol.can_verify:
                claims.append(Claim(kind='verify-firmware',
                                    icon='success',
                                    summary='Firmware can be verified after flashing',
                                    url='https://lvfs.readthedocs.io/en/latest/claims.html#verified-firmware'))
                if self.category and self.category.expect_device_checksum:
                    if self.device_checksums:
                        claims.append(Claim(kind='device-checksum',
                                            icon='success',
                                            summary='Firmware has attestation checksums',
                                            url='https://lvfs.readthedocs.io/en/latest/claims.html#device-checksums'))
                    else:
                        claims.append(Claim(kind='no-device-checksum',
                                            icon='warning',
                                            summary='Firmware has no attestation checksums',
                                            url='https://lvfs.readthedocs.io/en/latest/claims.html#device-checksums'))
            else:
                claims.append(Claim(kind='no-verify-firmware',
                                    icon='warning',
                                    summary='Firmware cannot be verified after flashing',
                                    url='https://lvfs.readthedocs.io/en/latest/claims.html#verified-firmware'))
        if self.checksum_contents:
            claims.append(Claim(kind='vendor-provenance',
                                icon='success',
                                summary='Added to the LVFS by {}'.format(self.fw.vendor.display_name),
                                url='https://lvfs.readthedocs.io/en/latest/claims.html#vendor-provenance'))
        if self.source_url:
            claims.append(Claim(kind='source-url',
                                icon='success',
                                summary='Source code available',
                                url='https://lvfs.readthedocs.io/en/latest/claims.html#source-url'))
        return claims

    @property
    def security_level(self):
        claims = {}
        for claim in self.autoclaims:
            claims[claim.kind] = claim
        if 'signed-firmware' in claims and 'device-checksum' in claims:
            return 2
        if 'signed-firmware' in claims:
            return 1
        return 0

    @property
    def requires_source_url(self):
        if self.project_license.find('GPL') != -1:
            return True
        return False

    @property
    def version_with_tag(self):
        if self.release_tag:
            return '{} ({})'.format(self.release_tag, self.version_display)
        return self.version_display

    @property
    def version_display(self):
        if self.version.isdigit():
            verfmt = self.verfmt_with_fallback
            if verfmt:
                return verfmt.uint32_to_str(int(self.version))
        return self.version

    @property
    def version_sections(self):
        if not self.version_display:
            return 0
        return len(self.version_display.split('.'))

    @property
    def problems(self):

        # verify update description
        if self.release_description:
            root = _xml_from_markdown(self.release_description)
            problems = _get_update_description_problems(root)
            # check for OEMs just pasting in the XML like before
            for element_name in ['p', 'li', 'ul', 'ol']:
                if self.release_description.find('<' + element_name + '>') != -1:
                    problems.append(Claim(kind='invalid-release-description',
                                          icon='warning',
                                          summary='No valid update description',
                                          description='Release description cannot contain XML markup'))
                    break
        else:
            problems = []
            problems.append(Claim(kind='no-release-description',
                                  icon='warning',
                                  summary='Release description is missing',
                                  description='All components should have a suitable update '
                                              'description before a firmware is moved to stable.\n'
                                              'Writing good quality release notes are really important '
                                              'as some users may be worried about an update that does '
                                              'not explain what it fixes.\n'
                                              'This also can be set in the .metainfo.xml file.'))

        # urgency is now a hard requirement
        if self.release_urgency == 'unknown':
            problems.append(Claim(kind='no-release-urgency',
                                  icon='warning',
                                  summary='Release urgency has not been set',
                                  description='All components should have an appropriate '
                                              'update urgency before a firmware is moved to stable.\n'
                                              'This also can be set in the .metainfo.xml file.'))

        # release timestamp is now a hard requirement
        if self.release_timestamp == 0:
            problems.append(Claim(kind='no-release-timestamp',
                                  icon='warning',
                                  summary='Release timestamp was not set',
                                  description='All components should have an appropriate '
                                              'update timestamp at upload time.\n'
                                              'This also can be set in the .metainfo.xml file.'))

        # we are going to be making policy decision on this soon
        if not self.protocol or self.protocol.value == 'unknown':
            problems.append(Claim(kind='no-protocol',
                                  icon='warning',
                                  summary='Update protocol has not been set',
                                  description='All components should have a defined update protocol '
                                              'before being moved to stable.\n'
                                              'This also can be set in the .metainfo.xml file.',
                                  url=url_for('components.route_show',
                                              component_id=self.component_id)))

        # check the GUIDs are indeed lowercase GUIDs (already done on upload)
        for guid in self.guids:
            if not _validate_guid(guid.value):
                problems.append(Claim(kind='invalid-guid',
                                      icon='warning',
                                      summary='Component GUID invalid',
                                      description='GUID {} is not valid'.format(guid.value),
                                      url=url_for('components.route_show',
                                                  component_id=self.component_id)))

        # check the version matches the expected section count
        if self.verfmt_with_fallback and \
           self.verfmt_with_fallback.value != 'plain' and \
           self.verfmt_with_fallback.sections:
            if self.version_sections != self.verfmt_with_fallback.sections:
                problems.append(Claim(kind='invalid-version-for-format',
                                      icon='warning',
                                      summary='Version format invalid',
                                      description='The version number {} incompatible with {}.'.\
                                                    format(self.version_display,
                                                           self.verfmt_with_fallback.value),
                                      url=url_for('components.route_show',
                                                  component_id=self.component_id)))

        # if the component and protocol both have verfmt, they must match
        if self.verfmt and self.protocol and self.protocol.verfmt:
            if self.verfmt.value != self.protocol.verfmt.value:
                problems.append(Claim(kind='invalid-format-for-protocol',
                                      icon='warning',
                                      summary='Version vormat {} incompatible with protocol-defined {}'.\
                                                    format(self.verfmt.value,
                                                           self.protocol.verfmt.value),
                                      url=url_for('components.route_show',
                                                  component_id=self.component_id)))

        # we are going to be uing this in the UI soon
        if not self.category or self.category.value == 'unknown':
            problems.append(Claim(kind='no-category',
                                  icon='warning',
                                  summary='Firmware category has not been set',
                                  description='All components should have a defined update category '
                                              'before being moved to stable.\n'
                                              'This also can be set in the .metainfo.xml file.',
                                  url=url_for('components.route_show',
                                              component_id=self.component_id)))

        # firmware can't be pushed to public with a private protocol
        if self.protocol and not self.protocol.is_public:
            problems.append(Claim(kind='no-protocol',
                                  icon='warning',
                                  summary='Update protocol is not public',
                                  url=url_for('components.route_show',
                                              component_id=self.component_id)))

        # some firmware requires a source URL
        if self.requires_source_url and not self.source_url:
            problems.append(Claim(kind='no-source',
                                  icon='warning',
                                  summary='Update does not link to source code',
                                  description='Firmware that uses the GNU General Public License has to '
                                              'provide a link to the source code used to build the firmware.',
                                  url=url_for('components.route_show',
                                              component_id=self.component_id,
                                              page='update')))

        # the URL has to be valid if provided
        if self.details_url and not _is_valid_url(self.details_url):
            problems.append(Claim(kind='invalid-details-url',
                                  icon='warning',
                                  summary='The update details URL was provided but not valid',
                                  url=url_for('components.route_show',
                                              page='update',
                                              component_id=self.component_id)))
        if self.source_url and not _is_valid_url(self.source_url):
            problems.append(Claim(kind='invalid-source-url',
                                  icon='warning',
                                  summary='The release source URL was provided but not valid',
                                  url=url_for('components.route_show',
                                              page='update',
                                              component_id=self.component_id)))

        # the OEM doesn't manage this namespace
        values = [ns.value for ns in self.fw.vendor.namespaces]
        if not values:
            problems.append(Claim(kind='no-vendor-namespace',
                                  icon='warning',
                                  summary='No AppStream namespace for vendor',
                                  description='Your vendor does not have permission to own this AppStream ID '
                                              'component prefix.\n'
                                              'Please either change the firmware vendor or contact the '
                                              'LVFS administrator to fix this.'))
        elif self.appstream_id_prefix not in values:
            problems.append(Claim(kind='invalid-vendor-namespace',
                                  icon='warning',
                                  summary='Invalid vendor namespace',
                                  description='{} does not have permission to own the AppStream ID '
                                              'component prefix of {}.\n'
                                              'Please either change the vendor to the correct OEM or contact '
                                              'the LVFS administrator to fix this.'.\
                                                    format(self.fw.vendor_odm.display_name,
                                                           self.appstream_id_prefix),
                                  url=url_for('firmware.route_affiliation',
                                              firmware_id=self.fw.firmware_id)))

        # name_variant_suffix contains a word in the name
        if self.name_variant_suffix:
            nvs_words = self.name_variant_suffix.split(' ')
            nvs_kws = [_sanitize_keyword(word) for word in nvs_words]
            for word in self.name.split(' '):
                if _sanitize_keyword(word) in nvs_kws:
                    problems.append(Claim(kind='invalid-name-variant-suffix',
                                          icon='warning',
                                          summary='{} is already part of the <name>'.format(word),
                                          url=url_for('components.route_show',
                                                      component_id=self.component_id)))

        # add all CVE problems
        for issue in self.issues:
            if issue.problem:
                problems.append(issue.problem)

        # set the URL for the component
        for problem in problems:
            if problem.url:
                continue
            problem.url = url_for('components.route_show',
                                  component_id=self.component_id,
                                  page='update')
        return problems

    @property
    def has_complex_requirements(self):
        seen = []
        for rq in self.requirements:
            if rq.kind == 'firmware':
                if rq.value not in [None, 'bootloader']:
                    return True
                if rq.depth:
                    return True
            key = rq.kind + ':' + str(rq.value)
            if key in seen:
                return True
            seen.append(key)
        return False

    def add_keywords_from_string(self, value, priority=0):
        existing_keywords = {}
        for kw in self.keywords:
            existing_keywords[kw.value] = kw
        for keyword in _split_search_string(value):
            if keyword in existing_keywords:
                continue
            self.keywords.append(Keyword(value=keyword, priority=priority))

    def find_req(self, kind, value):
        """ Find a Requirement from the kind and/or value """
        for rq in self.requirements:
            if rq.kind != kind:
                continue
            if rq.value != value:
                continue
            return rq
        return None

    def add_claim(self, claim):
        for component_claim in self.component_claims:
            if component_claim.claim.kind == claim.kind:
                return
        self.component_claims.append(ComponentClaim(claim=claim))

    def check_acl(self, action, user=None):

        # fall back
        if not user:
            user = g.user
        if user.check_acl('@admin'):
            return True

        # depends on the action requested
        if action == '@modify-updateinfo':
            if not self.fw.remote.is_public:
                if user.check_acl('@qa') and self.fw._is_permitted_action(action, user):
                    return True
                if self.fw._is_owner(user):
                    return True
            return False
        if action in ('@modify-keywords', '@modify-requirements', '@modify-checksums'):
            if user.check_acl('@qa') and self.fw._is_permitted_action(action, user):
                return True
            if self.fw._is_owner(user):
                return True
            return False
        raise NotImplementedError('unknown security check action: %s:%s' % (self, action))

    def __repr__(self):
        return "Component object %s" % self.appstream_id

class Remote(db.Model):

    __tablename__ = 'remotes'

    remote_id = Column(Integer, primary_key=True)
    name = Column(Text, nullable=False)
    is_public = Column(Boolean, default=False)
    is_dirty = Column(Boolean, default=False)

    vendors = relationship("Vendor", back_populates="remote")
    fws = relationship("Firmware")

    def check_fw(self, fw):
        # remote is specified exactly
        if self.remote_id == fw.remote.remote_id:
            return True
        # odm uploaded to oem remote, but also include for odm
        if not self.is_public and fw.vendor_odm in self.vendors:
            return True
        return False

    @property
    def is_deleted(self):
        return self.name == 'deleted'

    @property
    def icon_name(self):
        if self.name in ['private', 'testing', 'stable']:
            return self.name
        if self.name == 'deleted':
            return 'trash'
        if self.name.startswith('embargo'):
            return 'embargo'
        return None

    @property
    def description(self):
        if self.name == 'private':
            return 'Only available to you'
        if self.name in ['testing', 'stable']:
            return 'Available to the public'
        if self.name == 'deleted':
            return 'Deleted'
        if self.name.startswith('embargo'):
            return 'Embargoed'
        return None

    @property
    def is_signed(self):
        return self.name != 'deleted' and self.name != 'private'

    @property
    def filename(self):
        if self.name == 'private':
            return None
        if self.name == 'stable':
            return 'firmware.xml.gz'
        if self.name == 'testing':
            return 'firmware-testing.xml.gz'
        return 'firmware-%s.xml.gz' % _qa_hash(self.name[8:])

    @property
    def scheduled_signing(self):
        now = datetime.datetime.now()
        if self.is_public:
            secs = (((4 - (now.hour % 4)) * 60) + (60 - now.minute)) * 60 + (60 - now.second)
        else:
            secs = ((5 - (now.minute % 5)) * 60) + (60 - now.second)
        return datetime.datetime.now() + datetime.timedelta(seconds=secs)

    def __repr__(self):
        return "Remote object %s [%s]" % (self.remote_id, self.name)

class FirmwareEvent(db.Model):

    __tablename__ = 'firmware_events'

    firmware_event_id = Column(Integer, primary_key=True)
    firmware_id = Column(Integer, ForeignKey('firmware.firmware_id'), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey('users.user_id'), nullable=False)
    timestamp = Column(DateTime, nullable=False, default=datetime.datetime.utcnow)
    remote_id = Column(Integer, ForeignKey('remotes.remote_id'), nullable=False)

    fw = relationship("Firmware", back_populates="events")

    user = relationship('User', foreign_keys=[user_id])
    remote = relationship('Remote', foreign_keys=[remote_id], lazy='joined')

    def __repr__(self):
        return "FirmwareEvent object %s" % self.firmware_event_id

class FirmwareLimit(db.Model):

    __tablename__ = 'firmware_limits'

    firmware_limit_id = Column(Integer, primary_key=True)
    firmware_id = Column(Integer, ForeignKey('firmware.firmware_id'), nullable=False, index=True)
    value = Column(Integer, nullable=False)
    user_agent_glob = Column(Text, default=None)
    response = Column(Text, default=None)

    fw = relationship("Firmware", back_populates="limits")

class Firmware(db.Model):

    __tablename__ = 'firmware'

    firmware_id = Column(Integer, primary_key=True)
    vendor_id = Column(Integer, ForeignKey('vendors.vendor_id'), nullable=False, index=True)
    addr = Column(String(40), nullable=False)
    timestamp = Column(DateTime, nullable=False, default=datetime.datetime.utcnow)
    filename = Column(Text, nullable=False)
    download_cnt = Column(Integer, default=0)
    checksum_upload_sha1 = Column(String(40), nullable=False, index=True)
    checksum_upload_sha256 = Column(String(64), nullable=False)
    _version_display = Column('version_display', Text, nullable=True, default=None)
    remote_id = Column(Integer, ForeignKey('remotes.remote_id'), nullable=False, index=True)
    checksum_signed_sha1 = Column(String(40), nullable=False)
    checksum_signed_sha256 = Column(String(64), nullable=False)
    user_id = Column(Integer, ForeignKey('users.user_id'), nullable=False, index=True)
    signed_timestamp = Column(DateTime, default=None)
    is_dirty = Column(Boolean, default=False)           # waiting to be included in metadata
    _banned_country_codes = Column('banned_country_codes', Text, default=None) # ISO 3166, delimiter ','
    report_success_cnt = Column(Integer, default=0)     # updated by cron.py
    report_failure_cnt = Column(Integer, default=0)     # updated by cron.py
    report_issue_cnt = Column(Integer, default=0)       # updated by cron.py
    failure_minimum = Column(Integer, default=0)
    failure_percentage = Column(Integer, default=0)
    _do_not_track = Column('do_not_track', Boolean, default=False)

    mds = relationship("Component",
                       back_populates="fw",
                       lazy='joined',
                       cascade='all,delete-orphan')
    events = relationship("FirmwareEvent",
                          back_populates="fw",
                          cascade='all,delete-orphan')
    reports = relationship("Report",
                           back_populates="fw",
                           cascade='all,delete-orphan')
    clients = relationship("Client",
                           back_populates="fw",
                           cascade='all,delete-orphan')
    limits = relationship("FirmwareLimit",
                          back_populates="fw",
                          cascade='all,delete-orphan')
    tests = relationship("Test",
                         order_by="desc(Test.scheduled_ts)",
                         back_populates="fw",
                         cascade='all,delete-orphan')
    analytics = relationship("AnalyticFirmware",
                             back_populates="firmware",
                             cascade='all,delete-orphan')

    vendor = relationship('Vendor', foreign_keys=[vendor_id])
    user = relationship('User', foreign_keys=[user_id])
    remote = relationship('Remote', foreign_keys=[remote_id], lazy='joined')

    @property
    def vendor_odm(self):
        if not self.user:
            return None
        return self.user.vendor

    @property
    def target_duration(self):
        if not self.events:
            return 0
        return datetime.datetime.utcnow() - self.events[-1].timestamp.replace(tzinfo=None)

    @property
    def do_not_track(self):
        return self._do_not_track or self.vendor.do_not_track

    @property
    def is_deleted(self):
        return self.remote.is_deleted

    @property
    def banned_country_codes(self):
        if self._banned_country_codes:
            return self._banned_country_codes
        return self.vendor.banned_country_codes

    @property
    def get_possible_users_to_email(self):
        users = []

        # vendor that owns the firmware
        for u in self.vendor.users:
            if u.check_acl('@qa') or u.check_acl('@vendor-manager'):
                users.append(u)

        # odm that uploaded the firmware
        if self.vendor != self.vendor_odm:
            for u in self.vendor_odm.users:
                if u.check_acl('@qa') or u.check_acl('@vendor-manager'):
                    users.append(u)
        return users

    @property
    def success(self):
        total = self.report_failure_cnt + self.report_success_cnt
        if not total:
            return None
        return (self.report_success_cnt * 100) / total

    @property
    def filename_absolute(self):
        if self.is_deleted:
            return os.path.join('/deleted', self.filename)
        return os.path.join('/downloads', self.filename)

    @property
    def color(self):
        if self.success is None:
            return 'secondary'
        if self.success > 95:
            return 'success'
        if self.success > 80:
            return 'warning'
        return 'danger'

    @property
    def names(self):
        names = []
        for md in self.mds:
            names.extend(md.names)
        return names

    @property
    def is_failure(self):
        if not self.report_failure_cnt:
            return False
        if not self.failure_minimum:
            return False
        if not self.failure_percentage:
            return False
        if self.report_failure_cnt < self.failure_minimum:
            return False
        return self.success < self.failure_percentage

    @property
    def inhibit_download(self):
        for md in self.mds:
            if md.inhibit_download:
                return True
        return False

    def find_test_by_plugin_id(self, plugin_id):
        for test in self.tests:
            if test.plugin_id == plugin_id:
                return test
        return None

    @property
    def autoclaims(self):
        # return the smallest of all the components, i.e. the least secure
        md_lowest = None
        claims = []
        for md in self.mds:
            if not md_lowest or md.security_level < md_lowest.security_level:
                md_lowest = md
                claims = md.autoclaims

        # been virus checked
        test = self.find_test_by_plugin_id('clamav')
        if test and test.ended_ts and test.success:
            claims.append(Claim(kind='virus-safe',
                                icon='success',
                                summary='Virus checked using ClamAV',
                                url='https://lvfs.readthedocs.io/en/latest/claims.html#virus-safe'))
        return claims

    @property
    def claims(self):
        claims = []
        for md in self.mds:
            for claim in md.claims:
                if claim not in claims:
                    claims.append(claim)
        return claims

    @property
    def scheduled_signing(self):
        now = datetime.datetime.now()
        secs = ((5 - (now.minute % 5)) * 60) + (60 - now.second)
        return datetime.datetime.now() + datetime.timedelta(seconds=secs)

    @property
    def version_display(self):
        if self._version_display:
            return self._version_display
        md_versions = []
        for md in self.mds:
            if not md.version_display:
                continue
            if md.version_display not in md_versions:
                md_versions.append(md.version_display)
        return ', '.join(md_versions)

    @property
    def md_prio(self):
        md_prio = None
        for md in self.mds:
            if not md_prio or md.priority > md_prio.priority:
                md_prio = md
        return md_prio

    @version_display.setter
    def version_display(self, value):
        self._version_display = value

    @property
    def problems(self):
        # does the firmware have any warnings
        problems = []
        if self.is_deleted:
            problems.append(Claim(kind='deleted',
                                  icon='trash',
                                  summary='Firmware has been deleted',
                                  description='Once a file has been deleted on the LVFS it must be '
                                              'undeleted before it can be moved to a different target.',
                                  url=url_for('firmware.route_show', firmware_id=self.firmware_id)))
        if not self.signed_timestamp:
            problems.append(Claim(kind='unsigned',
                                  icon='waiting',
                                  summary='Firmware is unsigned',
                                  description='Signing a firmware file on the LVFS is automatic and will '
                                              'be completed soon.\n'
                                              'You can refresh this page to find out when the firmware '
                                              'has been signed.',
                                  url=url_for('firmware.route_show', firmware_id=self.firmware_id)))
        # test failures
        for test in self.tests:
            if not test.started_ts:
                problems.append(Claim(kind='test-pending',
                                      icon='waiting',
                                      summary='Runtime test {} is pending'.format(test.plugin_id),
                                      description='The LVFS runs tests on certain types of firmware to check they '
                                                  'are valid.\n'
                                                  'Some tests are still pending and will be completed shortly.\n'
                                                  'You can refresh this page to find out when the firmware has '
                                                  'been tested.',
                                      url=url_for('firmware.route_tests', firmware_id=self.firmware_id)))
            elif not test.success and not test.waived_ts:
                if test.waivable:
                    problems.append(Claim(kind='test-failed',
                                          icon='warning',
                                          summary='Runtime test {} did not succeed'.format(test.plugin_id),
                                          description='A check on the firmware has failed.\n'
                                                      'This failure can be waived by a QA user and ignored.',
                                          url=url_for('firmware.route_tests', firmware_id=self.firmware_id)))
                else:
                    problems.append(Claim(kind='test-failed',
                                          icon='warning',
                                          summary='Runtime test {} did not succeed'.format(test.plugin_id),
                                          description='A non-waivable check on the firmware has failed.',
                                          url=url_for('firmware.route_tests', firmware_id=self.firmware_id)))
        for md in self.mds:
            for problem in md.problems:
                problem.md = md
                problems.append(problem)
        return problems

    def _is_owner(self, user):
        return self.user_id == user.user_id

    def _ensure_blobs(self):
        with open(_get_absolute_path(self), 'rb') as f:
            cabarchive = CabArchive(f.read())
        for md in self.mds:
            try:
                md._blob = cabarchive[md.filename_contents].buf
            except KeyError as _:
                pass

    def _is_vendor(self, user):
        return self.vendor_id == user.vendor_id

    def _is_odm(self, user):
        return self.vendor_odm.vendor_id == user.vendor_id

    def mark_dirty(self):
        self.is_dirty = True
        self.remote.is_dirty = True

    def _is_permitted_action(self, action, user):

        # is vendor
        if self._is_vendor(user):
            return True

        # the user is not a member of the ODM vendor
        if self.vendor_odm.vendor_id != user.vendor.vendor_id:
            return False

        # check ODM permissions
        aff = db.session.query(Affiliation).\
                               filter(Affiliation.vendor_id == self.vendor_id).\
                               filter(Affiliation.vendor_id_odm == user.vendor_id).\
                               first()
        if not aff:
            return False
        return aff.get_action(action)

    def check_acl(self, action, user=None):

        # fall back
        if not user:
            user = g.user
        if user.check_acl('@admin'):
            return True

        # depends on the action requested
        if action == '@delete':
            if self.is_deleted:
                return False
            if user.check_acl('@qa') and self._is_permitted_action(action, user):
                return True
            return False
        if action == '@nuke':
            if not self.is_deleted:
                return False
            return False
        if action == '@view':
            if user.check_acl('@qa') and self._is_permitted_action(action, user):
                return True
            if user.check_acl('@analyst') and self._is_permitted_action(action, user):
                return True
            if self._is_owner(user):
                return True
            return False
        if action == '@view-analytics':
            if not self.check_acl('@view', user):
                return False
            if user.check_acl('@qa') or user.check_acl('@analyst'):
                return True
            return False
        if action == '@undelete':
            if user.check_acl('@qa') and self._is_permitted_action(action, user):
                return True
            if self._is_owner(user):
                return True
            return False
        if action in ('@promote-stable', '@promote-testing'):
            if user.check_acl('@approved-public') and self._is_permitted_action(action, user):
                return True
            return False
        if action.startswith('@promote-'):
            if user.check_acl('@qa') and self._is_vendor(user):
                return True
            # ODM vendor can always move private<->embargo
            if self._is_odm(user):
                old = self.remote.name
                if old.startswith('embargo-'):
                    old = 'embargo'
                new = action[9:]
                if new.startswith('embargo-'):
                    new = 'embargo'
                if old in ('private', 'embargo') and new in ('private', 'embargo'):
                    return True
            return False
        if action == '@modify':
            if user.check_acl('@qa') and self._is_permitted_action(action, user):
                return True
            if self._is_owner(user):
                return True
            return False
        if action == '@modify-limit':
            if user.check_acl('@qa') and self._is_permitted_action(action, user):
                return True
            return False
        if action == '@modify-affiliation':
            if user.check_acl('@qa') and self._is_permitted_action(action, user):
                return True
            return False
        raise NotImplementedError('unknown security check action: %s:%s' % (self, action))

    def __repr__(self):
        return "Firmware object %s" % self.checksum_upload_sha1

class Client(db.Model):

    __tablename__ = 'clients'

    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime, nullable=False, default=datetime.datetime.utcnow, index=True)
    datestr = Column(Integer, default=0, index=True)
    addr = Column(String(40), nullable=False)
    firmware_id = Column(Integer, ForeignKey('firmware.firmware_id'), nullable=False, index=True)
    user_agent = Column(Text, default=None)

    fw = relationship('Firmware', foreign_keys=[firmware_id])

    def __repr__(self):
        return "Client object %s" % self.id

class Condition(db.Model):

    __tablename__ = 'conditions'

    condition_id = Column(Integer, primary_key=True)
    issue_id = Column(Integer, ForeignKey('issues.issue_id'), nullable=False, index=True)
    key = Column(Text, nullable=False)
    value = Column(Text, nullable=False)
    compare = Column(Text, default='eq', nullable=False)

    issue = relationship("Issue", back_populates="conditions")

    def matches(self, value):
        if self.compare == 'eq':
            return value == self.value
        if self.compare == 'lt':
            return vercmp(value, self.value) < 0
        if self.compare == 'le':
            return vercmp(value, self.value) <= 0
        if self.compare == 'gt':
            return vercmp(value, self.value) > 0
        if self.compare == 'ge':
            return vercmp(value, self.value) >= 0
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

    def __repr__(self):
        return "Condition object %s %s %s" % (self.key, self.compare, self.value)

class Issue(db.Model):

    __tablename__ = 'issues'

    issue_id = Column(Integer, primary_key=True)
    priority = Column(Integer, default=0)
    enabled = Column(Boolean, default=False)
    vendor_id = Column(Integer, ForeignKey('vendors.vendor_id'), nullable=False)
    url = Column(Text, default='')
    name = Column(Text, default=None)
    description = Column(Text, default='')
    conditions = relationship("Condition",
                              back_populates="issue",
                              cascade='all,delete-orphan')

    vendor = relationship('Vendor', foreign_keys=[vendor_id])

    def matches(self, data):
        """ if all conditions are satisfied from data """
        for condition in sorted(self.conditions, key=lambda x: x.relative_cost):
            if not condition.key in data:
                return False
            if not condition.matches(data[condition.key]):
                return False
        return True

    def check_acl(self, action, user=None):

        # fall back
        if not user:
            user = g.user
        if user.check_acl('@admin'):
            return True

        # depends on the action requested
        if action == '@create':
            return user.check_acl('@qa')
        if action == '@modify':
            if user.check_acl('@qa') and user.vendor_id == self.vendor_id:
                return True
            return False
        if action == '@view':
            if user.check_acl('@qa') and user.vendor_id == self.vendor_id:
                return True
            # any issues owned by admin can be viewed by a QA user
            if user.check_acl('@qa') and self.vendor_id == 1:
                return True
            return False
        raise NotImplementedError('unknown security check action: %s:%s' % (self, action))

    def __repr__(self):
        return "Issue object %s" % self.url

class ReportAttribute(db.Model):
    __tablename__ = 'report_attributes'

    report_attribute_id = Column(Integer, primary_key=True)
    report_id = Column(Integer, ForeignKey('reports.report_id'), nullable=False, index=True)
    key = Column(Text, nullable=False)
    value = Column(Text, default=None)

    report = relationship("Report", back_populates="attributes")

    def __repr__(self):
        return "ReportAttribute object %s=%s" % (self.key, self.value)

class Report(db.Model):

    __tablename__ = 'reports'

    report_id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime, nullable=False, default=datetime.datetime.utcnow)
    state = Column(Integer, default=0)
    machine_id = Column(String(64), nullable=False)
    firmware_id = Column(Integer, ForeignKey('firmware.firmware_id'), nullable=False, index=True)
    checksum = Column(String(64), nullable=False) # remove?
    issue_id = Column(Integer, default=0)
    user_id = Column(Integer, ForeignKey('users.user_id'), default=None)

    fw = relationship('Firmware', foreign_keys=[firmware_id])
    user = relationship('User', foreign_keys=[user_id])
    attributes = relationship("ReportAttribute",
                              back_populates="report",
                              lazy='joined',
                              cascade='all,delete-orphan')

    @property
    def color(self):
        if self.state == 1:
            return 'info'
        if self.state == 2:
            return 'success'
        if self.state == 3:
            if self.issue_id:
                return 'info'
            return 'danger'
        if self.state == 4:
            return 'info'
        return 'danger'

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

    def check_acl(self, action, user=None):

        # fall back
        if not user:
            user = g.user
        if user.check_acl('@admin'):
            return True

        # depends on the action requested
        if action == '@delete':
            # only admin
            return False
        if action == '@view':
            # QA user can modify any issues matching vendor_id
            if user.check_acl('@qa') and self.fw._is_vendor(user):
                return True
            return False
        raise NotImplementedError('unknown security check action: %s:%s' % (self, action))

    def __repr__(self):
        return "Report object %s" % self.report_id

class Metric(db.Model):

    __tablename__ = 'metrics'

    setting_id = Column(Integer, primary_key=True)
    key = Column(Text, nullable=False)
    value = Column(Integer, default=0)

    def __repr__(self):
        return 'Metric object {}={}'.format(self.key, self.value)

class Setting(db.Model):

    __tablename__ = 'settings'

    setting_id = Column(Integer, primary_key=True)
    key = Column('config_key', Text)
    value = Column('config_value', Text)

    def __repr__(self):
        return "Setting object %s" % self.key

def _get_datestr_from_datetime(when):
    return int("%04i%02i%02i" % (when.year, when.month, when.day))

class Analytic(db.Model):

    __tablename__ = 'analytics'

    datestr = Column(Integer, primary_key=True)
    cnt = Column(Integer, default=1)

    def __repr__(self):
        return "Analytic object %s" % self.datestr

class AnalyticVendor(db.Model):

    __tablename__ = 'analytics_vendor'

    analytic_id = Column(Integer, primary_key=True)
    datestr = Column(Integer, default=0, index=True)
    vendor_id = Column(Integer, ForeignKey('vendors.vendor_id'), nullable=False, index=True)
    cnt = Column(Integer, default=0)

    vendor = relationship('Vendor', foreign_keys=[vendor_id])

    def __repr__(self):
        return "AnalyticVendor object %s:%s" % (self.datestr, self.vendor_id)

class AnalyticFirmware(db.Model):

    __tablename__ = 'analytics_firmware'

    analytic_id = Column(Integer, primary_key=True)
    datestr = Column(Integer, default=0, index=True)
    firmware_id = Column(Integer, ForeignKey('firmware.firmware_id'), nullable=False, index=True)
    cnt = Column(Integer, default=0)

    firmware = relationship('Firmware', foreign_keys=[firmware_id])

    def __repr__(self):
        return "AnalyticFirmware object %s:%s" % (self.datestr, self.firmware_id)

class UseragentKind(IntEnum):
    APP = 0
    FWUPD = 1
    LANG = 2
    DISTRO = 3

class Useragent(db.Model):

    __tablename__ = 'useragents'

    useragent_id = Column(Integer, primary_key=True)
    kind = Column(Integer, default=0, index=True)
    datestr = Column(Integer, default=0)
    value = Column(Text, default=None)
    cnt = Column(Integer, default=1)

    def __repr__(self):
        return 'Useragent object {}:{}'.format(self.kind, self.datestr)

class Protocol(db.Model):

    __tablename__ = 'protocol'

    protocol_id = Column(Integer, primary_key=True)
    value = Column(Text, nullable=False)
    name = Column(Text, default=None)
    is_signed = Column(Boolean, default=False)
    is_public = Column(Boolean, default=False)
    can_verify = Column(Boolean, default=False)
    has_header = Column(Boolean, default=False)
    verfmt_id = Column(Integer, ForeignKey('verfmts.verfmt_id'))

    verfmt = relationship('Verfmt', foreign_keys=[verfmt_id])

    def __repr__(self):
        return "Protocol object %s:%s" % (self.protocol_id, self.value)

class SearchEvent(db.Model):

    __tablename__ = 'search_events'

    search_event_id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime, nullable=False, default=datetime.datetime.utcnow)
    addr = Column(String(40), nullable=False)
    value = Column(Text, nullable=False)
    count = Column(Integer, default=0)
    method = Column(Text, default=None)

    def __repr__(self):
        return "SearchEvent object %s" % self.search_event_id
