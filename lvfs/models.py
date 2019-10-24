#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2015-2018 Richard Hughes <richard@hughsie.com>
#
# SPDX-License-Identifier: GPL-2.0+
#
# pylint: disable=too-few-public-methods,too-many-instance-attributes
# pylint: disable=too-many-arguments,too-many-lines,protected-access,wrong-import-position

import os
import datetime
import fnmatch
import functools
import zlib
import re
import math
import hashlib
import collections

from enum import Enum

import onetimepass

from flask import g, url_for
from werkzeug.security import generate_password_hash, check_password_hash

from sqlalchemy import Column, Integer, Float, String, Text, Boolean, DateTime, ForeignKey, Index
from sqlalchemy.ext.associationproxy import association_proxy
from sqlalchemy.orm import relationship

from lvfs import db
from cabarchive import CabArchive
from pkgversion import vercmp

from .dbutils import _execute_count_star
from .hash import _qa_hash, _password_hash, _otp_hash
from .util import _generate_password, _xml_from_markdown, _get_update_description_problems
from .util import _get_absolute_path, _get_shard_path

class SecurityClaim:

    def __init__(self):
        self.attrs = {}

    def add_attr(self, attr, detail=None):

        # append the attribute if it does not exist
        if attr not in self.attrs:
            self.attrs[attr] = detail

    @property
    def rating(self):
        if 'success-signed-firmware' in self.attrs and 'success-device-checksum' in self.attrs:
            return 2
        if 'success-signed-firmware' in self.attrs:
            return 1
        return 0

    def __repr__(self):
        return "SecurityClaim object %s" % self.attrs

class Problem:
    def __init__(self, kind, description=None, url=None, md=None):
        self.kind = kind
        self.description = description
        self.url = url
        self.md = md

    @property
    def summary(self):
        if self.kind == 'unsigned':
            return 'Firmware is unsigned'
        if self.kind == 'deleted':
            return 'Firmware has been deleted'
        if self.kind == 'no-release-urgency':
            return 'No update urgency'
        if self.kind == 'no-release-timestamp':
            return 'No update timestamp'
        if self.kind == 'no-release-description':
            return 'No update description'
        if self.kind == 'invalid-release-description':
            return 'No valid update description'
        if self.kind == 'no-protocol':
            return 'No update protocol set'
        if self.kind == 'no-category':
            return 'No firmware category set'
        if self.kind == 'test-failed':
            return 'Firmware is not valid'
        if self.kind == 'test-pending':
            return 'Firmware tests are pending'
        if self.kind == 'no-source':
            return 'No source code link'
        if self.kind == 'no-vendor-namespace':
            return 'No vendor namespaces set'
        if self.kind == 'invalid-vendor-namespace':
            return 'Invalid vendor namespace'
        if self.kind == 'invalid-details-url':
            return 'Invalid details URL'
        if self.kind == 'invalid-source-url':
            return 'Invalid source URL'
        return 'Unknown problem %s' % self.kind

    @property
    def icon_name(self):
        if self.kind == 'unsigned':
            return 'task-due'
        if self.kind == 'deleted':
            return 'emblem-readonly'
        return 'dialog-warning'

class Agreement(db.Model):

    # database
    __tablename__ = 'agreements'
    __table_args__ = {'mysql_character_set': 'utf8mb4'}

    agreement_id = Column(Integer, primary_key=True, unique=True, nullable=False)
    created = Column(DateTime, nullable=False, default=datetime.datetime.utcnow)
    version = Column(Integer, nullable=False)
    text = Column(Text, default=None)

class User(db.Model):

    # database
    __tablename__ = 'users'
    __table_args__ = (Index('idx_users_username_password', 'username', 'password'),
                      {'mysql_character_set': 'utf8mb4'}
                     )

    user_id = Column(Integer, primary_key=True, unique=True, nullable=False)
    username = Column(String(80), nullable=False, index=True)
    password_hash = Column('password', String(128), default=None)
    password_ts = Column(DateTime, default=None)
    password_recovery = Column(String(40), default=None)
    password_recovery_ts = Column(DateTime, default=None)
    otp_secret = Column(String(16))
    display_name = Column(Text, default=None)
    vendor_id = Column(Integer, ForeignKey('vendors.vendor_id'), nullable=False)
    auth_type = Column(Text, default='disabled')
    auth_warning = Column(Text, default=None)
    is_qa = Column(Boolean, default=False)
    is_robot = Column(Boolean, default=False)
    is_analyst = Column(Boolean, default=False)
    is_vendor_manager = Column(Boolean, default=False)
    is_approved_public = Column(Boolean, default=False)
    is_admin = Column(Boolean, default=False)
    is_researcher = Column(Boolean, default=False)
    is_otp_enabled = Column(Boolean, default=False)
    is_otp_working = Column(Boolean, default=False)
    agreement_id = Column(Integer, ForeignKey('agreements.agreement_id'))
    ctime = Column(DateTime, nullable=False, default=datetime.datetime.utcnow)
    mtime = Column(DateTime, nullable=False, default=datetime.datetime.utcnow)
    atime = Column(DateTime, default=None)
    dtime = Column(DateTime, default=None)
    human_user_id = Column(Integer, ForeignKey('users.user_id'), nullable=True)
    notify_demote_failures = Column(Boolean, default=False)
    notify_server_error = Column(Boolean, default=False)
    notify_upload_vendor = Column(Boolean, default=False)
    notify_upload_affiliate = Column(Boolean, default=False)
    notify_promote = Column(Boolean, default=False)

    # link using foreign keys
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

    def __init__(self, username, password_hash=None, display_name=None,
                 vendor_id=None, auth_type='disabled', is_analyst=False, is_qa=False,
                 is_admin=False, is_vendor_manager=False, is_approved_public=False,
                 is_otp_enabled=False):
        """ Constructor for object """
        self.username = username
        self.password_hash = password_hash
        self.display_name = display_name
        self.auth_type = auth_type
        self.is_analyst = is_analyst
        self.is_qa = is_qa
        self.vendor_id = vendor_id
        self.is_admin = is_admin
        self.is_vendor_manager = is_vendor_manager
        self.is_approved_public = is_approved_public
        self.is_otp_enabled = is_otp_enabled

        # generate a random secret
        if self.otp_secret is None:
            self.otp_secret = _otp_hash()

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
        if (datetime.datetime.now() - self.ctime).total_seconds() > 60 * 60:
            return False

        # of required userclass
        return self.is_admin or self.is_vendor_manager

    def verify_totp(self, token):
        return onetimepass.valid_totp(token, self.otp_secret)

    def check_acl(self, action=None):

        # anyone who is an admin can do everything
        if self.is_admin:
            return True

        # disabled users can do nothing
        if self.auth_type == 'disabled':
            return False

        # decide based on the action
        if action == '@admin':
            return False
        if action == '@view-profile':
            return self.auth_type == 'local'
        if action == '@view-analytics':
            if self.is_qa or self.is_analyst:
                return True
            return False
        if action == '@manage-password':
            if self.auth_type == 'local':
                return True
            return False
        if action == '@yara-query':
            return self.is_researcher
        if action == '@add-attribute-researcher':
            if not self.vendor.check_acl('@manage-users'):
                return False
            return self.is_researcher
        if action == '@add-attribute-manager':
            if not self.vendor.check_acl('@manage-users'):
                return False
            return self.is_vendor_manager
        if action == '@add-attribute-approved':
            if not self.vendor.check_acl('@manage-users'):
                return False
            return self.is_approved_public
        if action == '@add-attribute-analyst':
            if not self.vendor.check_acl('@manage-users'):
                return False
            return self.is_analyst
        if action == '@add-attribute-qa':
            if not self.vendor.check_acl('@manage-users'):
                return False
            return self.is_qa
        if action == '@add-attribute-admin':
            if not self.vendor.check_acl('@manage-users'):
                return False
            return self.is_admin
        if action == '@add-attribute-robot':
            return self.vendor.check_acl('@manage-users')
        if action in ('@view-eventlog', '@view-issues'):
            return self.is_qa
        raise NotImplementedError('unknown security check type: %s' % self)

    def generate_password_recovery(self):
        if self.is_robot:
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

    # database
    __tablename__ = 'yara_query_result'
    __table_args__ = {'mysql_character_set': 'utf8mb4'}

    yara_query_result_id = Column(Integer, primary_key=True, unique=True, nullable=False)
    yara_query_id = Column(Integer, ForeignKey('yara_query.yara_query_id'), nullable=False)
    component_shard_id = Column(Integer, ForeignKey('component_shards.component_shard_id'), nullable=False)
    result = Column(Text, default=None)

    query = relationship('YaraQuery', foreign_keys=[yara_query_id])
    shard = relationship('ComponentShard', foreign_keys=[component_shard_id])

    def __repr__(self):
        return "<YaraQueryResult {}>".format(self.yara_query_result_id)

class YaraQuery(db.Model):

    # sqlalchemy metadata
    __tablename__ = 'yara_query'
    __table_args__ = {'mysql_character_set': 'utf8mb4'}

    yara_query_id = Column(Integer, primary_key=True, nullable=False, unique=True)
    user_id = Column(Integer, ForeignKey('users.user_id'), nullable=False)
    value = Column(Text, default=None)
    error = Column(Text, default=None)
    found = Column(Integer, default=0)
    total = Column(Integer, default=0)
    ctime = Column(DateTime, nullable=False, default=datetime.datetime.utcnow)
    started_ts = Column(DateTime, default=None)
    ended_ts = Column(DateTime, default=None)

    user = relationship('User', foreign_keys=[user_id])
    results = relationship("YaraQueryResult", cascade='all,delete-orphan')

    @property
    def color(self):
        if self.found and self.total:
            return 'warning'
        if self.total:
            return 'success'
        return 'info'

    @property
    def title(self):
        for line in self.value.split('\n'):
            if line.startswith('rule '):
                return line[5:]
        return None

    def check_acl(self, action, user=None):

        # fall back
        if not user:
            user = g.user
        if user.is_admin:
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

    # sqlalchemy metadata
    __tablename__ = 'restrictions'
    __table_args__ = {'mysql_character_set': 'utf8mb4'}

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

class Namespace(db.Model):

    # sqlalchemy metadata
    __tablename__ = 'namespaces'
    __table_args__ = {'mysql_character_set': 'utf8mb4'}

    namespace_id = Column(Integer, primary_key=True, unique=True, nullable=False)
    vendor_id = Column(Integer, ForeignKey('vendors.vendor_id'), nullable=False)
    value = Column(Text, nullable=False)
    ctime = Column(DateTime, nullable=False, default=datetime.datetime.utcnow)
    user_id = Column(Integer, ForeignKey('users.user_id'), nullable=False)

    # link back to parent
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

    # database
    __tablename__ = 'affiliation_actions'
    __table_args__ = {'mysql_character_set': 'utf8mb4'}

    affiliation_action_id = Column(Integer, primary_key=True, unique=True, nullable=False)
    affiliation_id = Column(Integer, ForeignKey('affiliations.affiliation_id'), nullable=False)
    ctime = Column(DateTime, nullable=False, default=datetime.datetime.utcnow)
    user_id = Column(Integer, ForeignKey('users.user_id'), nullable=False)
    action = Column(Text, default=None)

    user = relationship('User', foreign_keys=[user_id])
    affiliation = relationship('Affiliation', foreign_keys=[affiliation_id])

    def __repr__(self):
        return "<AffiliationAction {}>".format(self.action)

class Affiliation(db.Model):

    # database
    __tablename__ = 'affiliations'
    __table_args__ = {'mysql_character_set': 'utf8mb4'}

    affiliation_id = Column(Integer, primary_key=True, unique=True, nullable=False)
    timestamp = Column(DateTime, nullable=False, default=datetime.datetime.utcnow)
    vendor_id = Column(Integer, ForeignKey('vendors.vendor_id'), nullable=False)
    vendor_id_odm = Column(Integer, ForeignKey('vendors.vendor_id'), nullable=False)

    # link using foreign keys
    vendor = relationship("Vendor", foreign_keys=[vendor_id], back_populates="affiliations")
    vendor_odm = relationship("Vendor", foreign_keys=[vendor_id_odm])
    actions = relationship("AffiliationAction", cascade='all,delete-orphan')

    def __init__(self, vendor_id, vendor_id_odm):
        self.vendor_id = vendor_id
        self.vendor_id_odm = vendor_id_odm

    def get_action(self, action):
        for act in self.actions:
            if action == act.action:
                return act
        return None

    def __repr__(self):
        return "Affiliation object %s" % self.affiliation_id

class Vendor(db.Model):

    # sqlalchemy metadata
    __tablename__ = 'vendors'
    __table_args__ = {'mysql_character_set': 'utf8mb4'}

    vendor_id = Column(Integer, primary_key=True, unique=True)
    group_id = Column(String(80), nullable=False, index=True)
    display_name = Column(Text, default=None)
    internal_team = Column(Text, default=None)
    plugins = Column(Text, default=None)
    description = Column(Text, default=None)
    quote_text = Column(Text, default=None)
    quote_author = Column(Text, default=None)
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
    version_format = Column(String(10), default=None) # usually 'triplet' or 'quad'
    url = Column(Text, default=None)
    banned_country_codes = Column(Text, default=None) # ISO 3166, delimiter ','
    do_not_track = Column(Boolean, default=False)

    # magically get the users in this vendor group
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
    events = relationship("Event",
                          order_by="desc(Event.timestamp)",
                          lazy='dynamic',
                          cascade='all,delete-orphan')

    # link using foreign keys
    remote = relationship('Remote',
                          foreign_keys=[remote_id],
                          single_parent=True,
                          cascade='all,delete-orphan')

    def __init__(self, group_id=None, remote_id=None):
        """ Constructor for object """
        self.group_id = group_id
        self.display_name = None
        self.plugins = None
        self.description = None
        self.visible = False
        self.comments = None
        self.icon = None
        self.keywords = None
        self.quote_text = None
        self.quote_author = None
        self.remote_id = remote_id

    def get_sort_key(self):
        val = 0
        if self.fws_stable_recent:
            val += 0x100
        if self.fws_stable:
            val += 0x20
        if self.is_account_holder:
            val += 0x10
        return val

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
    @functools.lru_cache()
    def is_account_holder(self):
        return self.users

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
        if user.is_admin:
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
            # manager user can modify any users in his group
            if user.is_vendor_manager and user.vendor_id == self.vendor_id:
                return True
            return False
        if action == '@modify-oauth':
            return False
        if action == '@view-affiliations':
            return user.is_vendor_manager
        if action == '@modify-affiliations':
            return False
        if action == '@modify-affiliation-actions':
            return user.is_vendor_manager
        if action == '@view-exports':
            return user.is_qa or user.is_vendor_manager
        if action == '@modify-exports':
            return user.is_vendor_manager
        raise NotImplementedError('unknown security check action: %s:%s' % (self, action))

    def __repr__(self):
        return "Vendor object %s" % self.group_id

class Event(db.Model):

    # sqlalchemy metadata
    __tablename__ = 'event_log'
    __table_args__ = {'mysql_character_set': 'utf8mb4'}

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

class Certificate(db.Model):

    # sqlalchemy metadata
    __tablename__ = 'certificates'
    __table_args__ = {'mysql_character_set': 'utf8mb4'}

    certificate_id = Column(Integer, primary_key=True, nullable=False, unique=True)
    user_id = Column(Integer, ForeignKey('users.user_id'), nullable=False)
    ctime = Column(DateTime, nullable=False, default=datetime.datetime.utcnow)
    serial = Column(String(40), nullable=False)
    text = Column(Text, default=None)

    # link using foreign keys
    user = relationship('User', foreign_keys=[user_id])

    def __init__(self, user_id, serial=None, text=None):
        """ Constructor for object """
        self.user_id = user_id
        self.serial = serial
        self.text = text


    def check_acl(self, action, user=None):

        # fall back
        if not user:
            user = g.user
        if user.is_admin:
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

    # sqlalchemy metadata
    __tablename__ = 'requirements'
    __table_args__ = {'mysql_character_set': 'utf8mb4'}

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
    __table_args__ = {'mysql_character_set': 'utf8mb4'}

    keyword_id = Column(Integer, primary_key=True, unique=True, nullable=False)
    component_id = Column(Integer, ForeignKey('components.component_id'), nullable=False)
    priority = Column(Integer, default=0)
    value = Column(Text, nullable=False)

    # link back to parent
    md = relationship("Component", back_populates="keywords")

    def __init__(self, value, priority=0, md=None):
        """ Constructor for object """
        self.value = value
        self.priority = priority
        self.md = md

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

    # sqlalchemy metadata
    __tablename__ = 'checksums'
    __table_args__ = {'mysql_character_set': 'utf8mb4'}

    checksum_id = Column(Integer, primary_key=True, unique=True)
    component_id = Column(Integer, ForeignKey('components.component_id'), nullable=False)
    kind = Column(Text, nullable=False, default=None)
    value = Column(Text, nullable=False, default=None)

    # link back to parent
    md = relationship("Component")

    def __init__(self, value, kind='SHA1'):
        """ Constructor for object """
        self.kind = kind        # e.g. 'SHA1' or 'SHA256'
        self.value = value

    def __repr__(self):
        return "Checksum object %s(%s)" % (self.kind, self.value)

class TestAttribute(db.Model):
    __tablename__ = 'test_attributes'
    __table_args__ = {'mysql_character_set': 'utf8mb4'}

    test_attribute_id = Column(Integer, primary_key=True, nullable=False, unique=True)
    test_id = Column(Integer, ForeignKey('tests.test_id'), nullable=False)
    title = Column(Text, nullable=False)
    message = Column(Text, default=None)
    success = Column(Boolean, default=False)

    # link back to parent
    test = relationship("Test", back_populates="attributes")

    def __init__(self, test_id=0, title=None, message=None, success=True):
        """ Constructor for object """
        self.test_id = test_id
        self.title = title
        self.message = message
        self.success = success

    def __repr__(self):
        return "TestAttribute object %s=%s" % (self.title, self.message)

class Test(db.Model):

    # sqlalchemy metadata
    __tablename__ = 'tests'
    __table_args__ = {'mysql_character_set': 'utf8mb4'}

    test_id = Column(Integer, primary_key=True, unique=True, nullable=False)
    firmware_id = Column(Integer, ForeignKey('firmware.firmware_id'), nullable=False)
    plugin_id = Column(Text, default=None)
    waivable = Column(Boolean, default=False)
    scheduled_ts = Column(DateTime, nullable=False, default=datetime.datetime.utcnow)
    started_ts = Column(DateTime, default=None)
    ended_ts = Column(DateTime, default=None)
    waived_ts = Column(DateTime, default=None)
    waived_user_id = Column(Integer, ForeignKey('users.user_id'), nullable=True)
    max_age = Column(Integer, default=0)

    # link using foreign keys
    waived_user = relationship('User', foreign_keys=[waived_user_id])
    attributes = relationship("TestAttribute",
                              lazy='joined',
                              back_populates="test",
                              cascade='all,delete-orphan')

    # link back to parent
    fw = relationship("Firmware", back_populates="tests")

    def __init__(self, plugin_id, waivable=False, max_age=0):
        self.plugin_id = plugin_id
        self.waivable = waivable
        self.max_age = max_age

    def add_pass(self, title, message=None):
        self.attributes.append(TestAttribute(title=title, message=message))

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
        if user.is_admin:
            return True

        # depends on the action requested
        if action == '@retry':
            if user.is_qa and self.fw._is_permitted_action(action, user):
                return True
            if self.fw._is_owner(user):
                return True
            return False
        if action == '@waive':
            if user.is_qa and self.fw._is_permitted_action(action, user):
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

class Category(db.Model):

    # sqlalchemy metadata
    __tablename__ = 'categories'
    __table_args__ = {'mysql_character_set': 'utf8mb4'}

    category_id = Column(Integer, primary_key=True, nullable=False, unique=True)
    value = Column(Text, nullable=False)        # 'X-System'
    name = Column(Text, default=None)           # 'System Update'
    fallbacks = Column(Text, default=None)
    expect_device_checksum = Column(Boolean, default=False)

    def __init__(self, value, name=None, fallbacks=None, expect_device_checksum=False):
        """ Constructor for object """
        self.value = value
        self.name = name
        self.fallbacks = fallbacks
        self.expect_device_checksum = expect_device_checksum

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

class ComponentShardInfo(db.Model):

    # sqlalchemy metadata
    __tablename__ = 'component_shard_infos'
    __table_args__ = {'mysql_character_set': 'utf8mb4'}

    component_shard_info_id = Column(Integer, primary_key=True, unique=True, nullable=False)
    guid = Column(String(36), default=None, index=True)
    name = Column(Text, default=None)
    description = Column(Text, default=None)
    cnt = Column(Integer)

    # link using foreign keys
    shards = relationship("ComponentShard", cascade='all,delete-orphan')

    def __init__(self, guid=None, name=None, description=None):
        """ Constructor for object """
        self.cnt = 1
        self.guid = guid
        self.name = name
        self.description = description

    @property
    def description_with_fallback(self):
        if self.description:
            return self.description
        if self.name.endswith('Pei'):
            return 'The Pre-EFI Initialization phase is invoked early in the boot flow.'
        if self.name.endswith('Dxe'):
            return 'The Driver Execution Environment phase is where most of the system \
                    initialization is performed.'
        return None

    def __repr__(self):
        return "ComponentShardInfo object %s" % self.component_shard_info_id

class ComponentShardChecksum(db.Model):

    # sqlalchemy metadata
    __tablename__ = 'component_shard_checksums'
    __table_args__ = {'mysql_character_set': 'utf8mb4'}

    checksum_id = Column(Integer, primary_key=True, unique=True)
    component_shard_id = Column(Integer, ForeignKey('component_shards.component_shard_id'), nullable=False)
    kind = Column(Text, nullable=False, default=None)
    value = Column(Text, nullable=False, default=None)

    # link back to parent
    shard = relationship("ComponentShard")

    def __init__(self, value, kind='SHA1'):
        """ Constructor for object """
        self.kind = kind        # e.g. 'SHA1' or 'SHA256'
        self.value = value

    def __repr__(self):
        return "ComponentShardChecksum object %s(%s)" % (self.kind, self.value)

class ComponentShardCertificate(db.Model):

    # sqlalchemy metadata
    __tablename__ = 'component_shard_certificates'
    __table_args__ = {'mysql_character_set': 'utf8mb4'}

    component_shard_certificate_id = Column(Integer, primary_key=True, unique=True, nullable=False)
    component_shard_id = Column(Integer, ForeignKey('component_shards.component_shard_id'), nullable=False)
    kind = Column(Text, default=None)
    plugin_id = Column(Text, default=None)
    description = Column(Text, default=None)
    serial_number = Column(Text, default=None)
    not_before = Column(DateTime, default=None)
    not_after = Column(DateTime, default=None)

    # link back to parent
    shard = relationship('ComponentShard', back_populates="certificates")

    def __init__(self, component_shard_id=None, kind=None, description=None):
        """ Constructor for object """
        self.component_shard_id = component_shard_id
        self.kind = kind
        self.description = description
        self.serial_number = None
        self.not_before = None
        self.not_after = None

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

class ComponentShard(db.Model):

    # sqlalchemy metadata
    __tablename__ = 'component_shards'
    __table_args__ = {'mysql_character_set': 'utf8mb4'}

    component_shard_id = Column(Integer, primary_key=True, unique=True, nullable=False)
    component_id = Column(Integer, ForeignKey('components.component_id'), nullable=False)
    component_shard_info_id = Column(Integer,
                                     ForeignKey('component_shard_infos.component_shard_info_id'),
                                     nullable=False)
    plugin_id = Column(Text, default=None)
    size = Column(Integer, default=0)
    entropy = Column(Float, default=0.0)

    checksums = relationship("ComponentShardChecksum",
                             back_populates="shard",
                             cascade='all,delete-orphan',
                             lazy='joined')
    certificates = relationship("ComponentShardCertificate",
                                order_by="desc(ComponentShardCertificate.component_shard_certificate_id)",
                                back_populates='shard',
                                cascade='all,delete-orphan')
    info = relationship("ComponentShardInfo", lazy='joined')

    # link back to parent
    md = relationship('Component', back_populates="shards")

    def __init__(self, component_id=None, plugin_id=None):
        """ Constructor for object """
        self.component_id = component_id
        self.plugin_id = plugin_id
        self._blob = None

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
            csum = ComponentShardChecksum(hashlib.sha1(value).hexdigest(), 'SHA1')
            self.checksums.append(csum)

        # SHA256 is now the best we have
        if 'SHA256' in checksums:
            csum = ComponentShardChecksum(hashlib.sha256(value).hexdigest(), 'SHA256')
            self.checksums.append(csum)

    def save(self):
        fn = _get_shard_path(self)
        os.makedirs(os.path.dirname(fn), exist_ok=True)
        with open(fn, 'wb') as f:
            f.write(zlib.compress(self._blob))

    def ensure_info(self, guid, name):
        """ Find existing info object using the GUID, or create if not found """
        if self.info:
            return
        self.info = db.session.query(ComponentShardInfo).\
                            filter(ComponentShardInfo.guid == guid).first()
        if not self.info:
            self.info = ComponentShardInfo(guid, name)

        # overwrite just for a bit
        if self.info.name != name:
            self.info.name = name

    def __repr__(self):
        return "ComponentShard object %s" % self.component_shard_id

class ComponentIssue(db.Model):

    # sqlalchemy metadata
    __tablename__ = 'component_issues'
    __table_args__ = {'mysql_character_set': 'utf8mb4'}

    component_issue_id = Column(Integer, primary_key=True, unique=True, nullable=False, index=True)
    component_id = Column(Integer, ForeignKey('components.component_id'), nullable=False)
    kind = Column(Text, nullable=False)
    value = Column(Text, nullable=False)

    # link back to parent
    md = relationship("Component", back_populates="issues")

    @property
    def url(self):
        return 'https://nvd.nist.gov/vuln/detail/{}'.format(self.value)

    @property
    def problem(self):
        parts = self.value.split('-')
        if len(parts) != 3 or parts[0] != 'CVE':
            return Problem('invalid-issue', 'Format expected to be CVE-XXXX-XXXXX')
        if not parts[1].isnumeric:
            return Problem('invalid-issue', 'Expected year in CVE value')
        if int(parts[1]) < 1995:
            return Problem('invalid-issue', 'Invalid year in CVE value')
        if not parts[2].isnumeric:
            return Problem('invalid-issue', 'Expected integer in CVE token')
        return None

    def __repr__(self):
        return '<ComponentIssue {}>'.format(self.value)

def _is_valid_url(url):
    if not url.startswith('https://') and not url.startswith('http://'):
        return False
    return True

class ComponentClaim(db.Model):

    # sqlalchemy metadata
    __tablename__ = 'component_claims'
    __table_args__ = {'mysql_character_set': 'utf8mb4'}

    component_claim_id = Column(Integer, primary_key=True, unique=True, nullable=False, index=True)
    component_id = Column(Integer, ForeignKey('components.component_id'), nullable=False)
    kind = Column(Text, nullable=False)
    value = Column(Text, nullable=False)

    # link back to parent
    md = relationship("Component", back_populates="claims")

    def __repr__(self):
        return '<ComponentClaim {}>'.format(self.value)

class Component(db.Model):

    # sqlalchemy metadata
    __tablename__ = 'components'
    __table_args__ = {'mysql_character_set': 'utf8mb4'}

    component_id = Column(Integer, primary_key=True, unique=True, nullable=False, index=True)
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
    screenshot_url = Column(Text, default=None)
    screenshot_caption = Column(Text, default=None)
    inhibit_download = Column(Boolean, default=False)
    version_format = Column(String(10), default=None) # usually 'triplet' or 'quad'
    priority = Column(Integer, default=0)
    install_duration = Column(Integer, default=0)

    # link back to parent
    fw = relationship("Firmware", back_populates="mds", lazy='joined')

    # include all Component objects
    requirements = relationship("Requirement",
                                back_populates="md",
                                cascade='all,delete-orphan')
    issues = relationship('ComponentIssue',
                          back_populates='md',
                          cascade='all,delete-orphan')
    claims = relationship('ComponentClaim',
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
        self.details_url = None
        self.source_url = None
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
        self.priority = 0
        self._blob = None

    def __lt__(self, other):
        return vercmp(self.version, other.version) < 0

    def __eq__(self, other):
        return vercmp(self.version, other.version) == 0

    @property
    def blob(self):
        if not hasattr(self, '_blob'):
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
    def developer_name_display(self):
        if not self.developer_name:
            return None
        tmp = str(self.developer_name)
        for suffix in [' Limited', ' Ltd.', ' Inc.', ' Corp']:
            if tmp.endswith(suffix):
                return tmp[:-len(suffix)]
        return tmp

    @property
    def security_claim(self):
        sc = None
        if self.protocol:
            sc = self.protocol.security_claim
            if self.protocol.can_verify and self.category and self.category.expect_device_checksum:
                if self.device_checksums:
                    sc.add_attr('success-device-checksum', 'Firmware has attestation checksums')
                else:
                    sc.add_attr('warning-device-checksum', 'Firmware has no attestation checksums')
        if not sc:
            sc = SecurityClaim()
        for claim in self.claims:
            sc.add_attr(claim.kind, claim.value)
        if self.checksum_contents:
            sc.add_attr('success-contents-checksum', 'Added to the LVFS by %s' % self.fw.vendor.display_name)
        if self.source_url:
            sc.add_attr('success-source-url', 'Source code available')
        return sc

    @property
    def requires_source_url(self):
        if self.project_license.find('GPL') != -1:
            return True
        return False

    @property
    def version_display(self):
        if self.version.isdigit():
            version_format = self.version_format
            if not version_format:
                version_format = self.fw.vendor.version_format
            if not version_format:
                return self.version
            v = int(self.version)
            if version_format == 'quad':
                return '%02i.%02i.%02i.%02i' % ((v & 0xff000000) >> 24,
                                                (v & 0x00ff0000) >> 16,
                                                (v & 0x0000ff00) >> 8,
                                                v & 0x000000ff)
            if version_format == 'triplet':
                return '%02i.%02i.%04i' % ((v & 0xff000000) >> 24,
                                           (v & 0x00ff0000) >> 16,
                                           v & 0x0000ffff)
            if version_format == 'pair':
                return '%02i.%02i' % ((v & 0xffff0000) >> 16, v & 0x0000ffff)
            if version_format == 'intel-me':
                return '%i.%i.%i.%i' % (((v & 0xe0000000) >> 29) + 0x0b,
                                        (v & 0x1f000000) >> 24,
                                        (v & 0x00ff0000) >> 16,
                                        v &  0x0000ffff)
            if version_format == 'intel-me2':
                return '%i.%i.%i.%i' % ((v & 0xf0000000) >> 28,
                                        (v & 0x0f000000) >> 24,
                                        (v & 0x00ff0000) >> 16,
                                        v &  0x0000ffff)
            if version_format == 'bcd':
                return '%i.%i' % ((v & 0xf0) >> 4, v & 0x0f)
        return self.version

    @property
    def problems(self):

        # verify update description
        if self.release_description:
            root = _xml_from_markdown(self.release_description)
            problems = _get_update_description_problems(root)
            # check for OEMs just pasting in the XML like before
            for element_name in ['p', 'li', 'ul', 'ol']:
                if self.release_description.find('<' + element_name + '>') != -1:
                    problems.append(Problem('invalid-release-description',
                                            'Release description cannot contain XML markup'))
                    break
        else:
            problems = []
            problems.append(Problem('invalid-release-description',
                                    'Release description is missing'))

        # urgency is now a hard requirement
        if self.release_urgency == 'unknown':
            problems.append(Problem('no-release-urgency',
                                    'Release urgency has not been set'))

        # release timestamp is now a hard requirement
        if self.release_timestamp == 0:
            problems.append(Problem('no-release-timestamp',
                                    'Release timestamp was not set'))

        # we are going to be making policy decision on this soon
        if not self.protocol or self.protocol.value == 'unknown':
            problem = Problem('no-protocol',
                              'Update protocol has not been set')
            problem.url = url_for('.component_show',
                                  component_id=self.component_id)
            problems.append(problem)

        # we are going to be uing this in the UI soon
        if not self.category or self.category.value == 'unknown':
            problem = Problem('no-category',
                              'Firmware category has not been set')
            problem.url = url_for('.component_show',
                                  component_id=self.component_id)
            problems.append(problem)

        # firmware can't be pushed to public with a private protocol
        if self.protocol and not self.protocol.is_public:
            problem = Problem('no-protocol',
                              'Update protocol is not public')
            problem.url = url_for('.component_show',
                                  component_id=self.component_id)
            problems.append(problem)

        # some firmware requires a source URL
        if self.requires_source_url and not self.source_url:
            problem = Problem('no-source',
                              'Update does not link to source code')
            problem.url = url_for('.component_show',
                                  component_id=self.component_id,
                                  page='update')
            problems.append(problem)

        # the URL has to be valid if provided
        if self.details_url and not _is_valid_url(self.details_url):
            problem = Problem('invalid-details-url',
                              'The update details URL was provided but not valid')
            problem.url = url_for('.component_show',
                                  page='update',
                                  component_id=self.component_id)
            problems.append(problem)
        if self.source_url and not _is_valid_url(self.source_url):
            problem = Problem('invalid-source-url',
                              'The release source URL was provided but not valid')
            problem.url = url_for('.component_show',
                                  page='update',
                                  component_id=self.component_id)
            problems.append(problem)

        # the OEM doesn't manage this namespace
        values = [ns.value for ns in self.fw.vendor.namespaces]
        if not values:
            problem = Problem('no-vendor-namespace',
                              'No AppStream namespace values for '
                              'vendor {}'.format(self.fw.vendor_odm.group_id))
            problems.append(problem)
        elif self.appstream_id_prefix not in values:
            problem = Problem('invalid-vendor-namespace',
                              'Component ID {} not allowed '
                              'for vendor {}: {}'.format(self.appstream_id_prefix,
                                                         self.fw.vendor_odm.group_id,
                                                         ','.join(values)))
            problem.url = url_for('.firmware_affiliation',
                                  firmware_id=self.fw.firmware_id)
            problems.append(problem)

        # name_variant_suffix contains a word in the name
        if self.name_variant_suffix:
            nvs_words = self.name_variant_suffix.split(' ')
            nvs_kws = [_sanitize_keyword(word) for word in nvs_words]
            for word in self.name.split(' '):
                if _sanitize_keyword(word) in nvs_kws:
                    problem = Problem('invalid-name-variant-suffix',
                                      '{} is already part of the <name>'.format(word))
                    problem.url = url_for('.component_show',
                                          component_id=self.component_id)
                    problems.append(problem)

        # add all CVE problems
        for issue in self.issues:
            if issue.problem:
                problems.append(issue.problem)

        # set the URL for the component
        for problem in problems:
            if problem.url:
                continue
            problem.url = url_for('.component_show',
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
            self.keywords.append(Keyword(keyword, priority))

    def find_req(self, kind, value):
        """ Find a Requirement from the kind and/or value """
        for rq in self.requirements:
            if rq.kind != kind:
                continue
            if rq.value != value:
                continue
            return rq
        return None

    def add_claim(self, kind, value):
        for claim in self.claims:
            if claim.kind == kind:
                return
        self.claims.append(ComponentClaim(kind=kind, value=value))

    def check_acl(self, action, user=None):

        # fall back
        if not user:
            user = g.user
        if user.is_admin:
            return True

        # depends on the action requested
        if action == '@modify-updateinfo':
            if not self.fw.remote.is_public:
                if user.is_qa and self.fw._is_permitted_action(action, user):
                    return True
                if self.fw._is_owner(user):
                    return True
            return False
        if action in ('@modify-keywords', '@modify-requirements', '@modify-checksums'):
            if user.is_qa and self.fw._is_permitted_action(action, user):
                return True
            if self.fw._is_owner(user):
                return True
            return False
        raise NotImplementedError('unknown security check action: %s:%s' % (self, action))

    def __repr__(self):
        return "Component object %s" % self.appstream_id

class Remote(db.Model):

    # sqlalchemy metadata
    __tablename__ = 'remotes'
    __table_args__ = {'mysql_character_set': 'utf8mb4'}

    remote_id = Column(Integer, primary_key=True, unique=True, nullable=False)
    name = Column(Text, nullable=False)
    is_public = Column(Boolean, default=False)
    is_dirty = Column(Boolean, default=False)

    # link using foreign keys
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

    # sqlalchemy metadata
    __tablename__ = 'firmware_events'
    __table_args__ = {'mysql_character_set': 'utf8mb4'}

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

class FirmwareLimit(db.Model):

    # sqlalchemy metadata
    __tablename__ = 'firmware_limits'
    __table_args__ = {'mysql_character_set': 'utf8mb4'}

    firmware_limit_id = Column(Integer, primary_key=True, unique=True, nullable=False)
    firmware_id = Column(Integer, ForeignKey('firmware.firmware_id'), nullable=False)
    value = Column(Integer, nullable=False)
    user_agent_glob = Column(Text, default=None)
    response = Column(Text, default=None)

    # link back to parent
    fw = relationship("Firmware", back_populates="limits")

class Firmware(db.Model):

    # sqlalchemy metadata
    __tablename__ = 'firmware'
    __table_args__ = {'mysql_character_set': 'utf8mb4'}

    firmware_id = Column(Integer, primary_key=True, unique=True, nullable=False, index=True)
    vendor_id = Column(Integer, ForeignKey('vendors.vendor_id'), nullable=False)
    addr = Column(String(40), nullable=False)
    timestamp = Column(DateTime, nullable=False, default=datetime.datetime.utcnow)
    filename = Column(Text, nullable=False)
    download_cnt = Column(Integer, default=0)
    checksum_upload = Column(String(40), nullable=False, index=True)
    _version_display = Column('version_display', Text, nullable=True, default=None)
    remote_id = Column(Integer, ForeignKey('remotes.remote_id'), nullable=False)
    checksum_signed = Column(String(40), nullable=False)
    checksum_pulp = Column(String(64), nullable=False)
    user_id = Column(Integer, ForeignKey('users.user_id'), nullable=False)
    signed_timestamp = Column(DateTime, default=None)
    is_dirty = Column(Boolean, default=False)           # waiting to be included in metadata
    _banned_country_codes = Column('banned_country_codes', Text, default=None) # ISO 3166, delimiter ','
    report_success_cnt = Column(Integer, default=0)     # updated by cron.py
    report_failure_cnt = Column(Integer, default=0)     # updated by cron.py
    report_issue_cnt = Column(Integer, default=0)       # updated by cron.py
    failure_minimum = Column(Integer, default=0)
    failure_percentage = Column(Integer, default=0)
    _do_not_track = Column('do_not_track', Boolean, default=False)

    # include all Component objects
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

    # link using foreign keys
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
        return datetime.datetime.utcnow() - self.events[-1].timestamp

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
            if u.is_qa or u.is_vendor_manager:
                users.append(u)

        # odm that uploaded the firmware
        if self.vendor != self.vendor_odm:
            for u in self.vendor_odm.users:
                if u.is_qa or u.is_vendor_manager:
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
    def security_claim(self):
        # return the smallest of all the components, i.e. the least secure
        sc_lowest = None
        for md in self.mds:
            if not sc_lowest or md.security_claim.rating < sc_lowest.rating:
                sc_lowest = md.security_claim
        if not sc_lowest:
            sc_lowest = SecurityClaim()

        # been virus checked
        test = self.find_test_by_plugin_id('clamav')
        if test and test.ended_ts:
            if test.success:
                sc_lowest.add_attr('success-virus-safe', 'Virus checked using ClamAV')
            else:
                sc_lowest.add_attr('danger-virus-safe', 'Virus check using ClamAV failed')

        return sc_lowest

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
            problem = Problem('deleted')
            problem.url = url_for('.firmware_show', firmware_id=self.firmware_id)
            problems.append(problem)
        if not self.signed_timestamp:
            problem = Problem('unsigned')
            problem.url = url_for('.firmware_show', firmware_id=self.firmware_id)
            problems.append(problem)
        # test failures
        for test in self.tests:
            if not test.started_ts:
                problem = Problem('test-pending',
                                  'Runtime test %s is pending' % test.plugin_id)
                problem.url = url_for('.firmware_tests', firmware_id=self.firmware_id)
                problems.append(problem)
            elif not test.success and not test.waived_ts:
                problem = Problem('test-failed',
                                  'Runtime test %s did not succeed' % test.plugin_id)
                problem.url = url_for('.firmware_tests', firmware_id=self.firmware_id)
                problems.append(problem)
        for md in self.mds:
            for problem in md.problems:
                problem.md = md
                problems.append(problem)
        return problems

    def __init__(self):
        """ Constructor for object """
        self.addr = None
        self.timestamp = None
        self.filename = None        # filename of the original .cab file
        self.checksum_upload = None # SHA1 of the original .cab file
        self._version_display = None # from the firmware.inf file
        self.download_cnt = 0       # generated from the client database
        self.checksum_signed = None # SHA1 of the signed .cab
        self.user_id = None         # user_id of the uploader
        self.mds = []

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
        if user.is_admin:
            return True

        # depends on the action requested
        if action == '@delete':
            if self.is_deleted:
                return False
            if user.is_qa and self._is_permitted_action(action, user):
                return True
            return False
        if action == '@nuke':
            if not self.is_deleted:
                return False
            return False
        if action == '@view':
            if user.is_qa and self._is_permitted_action(action, user):
                return True
            if user.is_analyst and self._is_permitted_action(action, user):
                return True
            if self._is_owner(user):
                return True
            return False
        if action == '@view-analytics':
            if not self.check_acl('@view', user):
                return False
            if user.is_qa or user.is_analyst:
                return True
            return False
        if action == '@undelete':
            if user.is_qa and self._is_permitted_action(action, user):
                return True
            if self._is_owner(user):
                return True
            return False
        if action in ('@promote-stable', '@promote-testing'):
            if user.is_approved_public and self._is_permitted_action(action, user):
                return True
            return False
        if action.startswith('@promote-'):
            if user.is_qa and self._is_vendor(user):
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
            if user.is_qa and self._is_permitted_action(action, user):
                return True
            if self._is_owner(user):
                return True
            return False
        if action == '@modify-limit':
            if user.is_qa and self._is_permitted_action(action, user):
                return True
            return False
        if action == '@modify-affiliation':
            if user.is_qa and self._is_permitted_action(action, user):
                return True
            return False
        raise NotImplementedError('unknown security check action: %s:%s' % (self, action))

    def __repr__(self):
        return "Firmware object %s" % self.checksum_upload

class Client(db.Model):

    # sqlalchemy metadata
    __tablename__ = 'clients'
    __table_args__ = {'mysql_character_set': 'utf8mb4'}

    id = Column(Integer, primary_key=True, nullable=False, unique=True)
    timestamp = Column(DateTime, nullable=False, default=datetime.datetime.utcnow, index=True)
    datestr = Column(Integer, default=0, index=True)
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
        self.datestr = _get_datestr_from_datetime(datetime.datetime.utcnow())

    def __repr__(self):
        return "Client object %s" % self.id

class Condition(db.Model):

    # sqlalchemy metadata
    __tablename__ = 'conditions'
    __table_args__ = {'mysql_character_set': 'utf8mb4'}

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
    __table_args__ = {'mysql_character_set': 'utf8mb4'}

    issue_id = Column(Integer, primary_key=True, nullable=False, unique=True)
    priority = Column(Integer, default=0)
    enabled = Column(Boolean, default=False)
    vendor_id = Column(Integer, ForeignKey('vendors.vendor_id'), nullable=False)
    url = Column(Text, default='')
    name = Column(Text, default=None)
    description = Column(Text, default='')
    conditions = relationship("Condition",
                              back_populates="issue",
                              cascade='all,delete-orphan')

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

    def check_acl(self, action, user=None):

        # fall back
        if not user:
            user = g.user
        if user.is_admin:
            return True

        # depends on the action requested
        if action == '@create':
            return user.is_qa
        if action == '@modify':
            if user.is_qa and user.vendor_id == self.vendor_id:
                return True
            return False
        if action == '@view':
            if user.is_qa and user.vendor_id == self.vendor_id:
                return True
            # any issues owned by admin can be viewed by a QA user
            if user.is_qa and self.vendor_id == 1:
                return True
            return False
        raise NotImplementedError('unknown security check action: %s:%s' % (self, action))

    def __repr__(self):
        return "Issue object %s" % self.url

class ReportAttribute(db.Model):
    __tablename__ = 'report_attributes'
    __table_args__ = {'mysql_character_set': 'utf8mb4'}

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
    __table_args__ = {'mysql_character_set': 'utf8mb4'}

    report_id = Column(Integer, primary_key=True, nullable=False, unique=True)
    timestamp = Column(DateTime, nullable=False, default=datetime.datetime.utcnow)
    state = Column(Integer, default=0)
    machine_id = Column(String(64), nullable=False)
    firmware_id = Column(Integer, ForeignKey('firmware.firmware_id'), nullable=False, index=True)
    checksum = Column(String(64), nullable=False) # remove?
    issue_id = Column(Integer, default=0)
    user_id = Column(Integer, ForeignKey('users.user_id'), default=None)

    # link using foreign keys
    fw = relationship('Firmware', foreign_keys=[firmware_id])
    user = relationship('User', foreign_keys=[user_id])
    attributes = relationship("ReportAttribute",
                              back_populates="report",
                              lazy='joined',
                              cascade='all,delete-orphan')

    def __init__(self, firmware_id, machine_id=None, state=0, checksum=None, issue_id=0, user_id=None):
        """ Constructor for object """
        self.timestamp = None
        self.state = state
        self.machine_id = machine_id
        self.firmware_id = firmware_id
        self.issue_id = issue_id
        self.user_id = user_id
        self.checksum = checksum

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
        if user.is_admin:
            return True

        # depends on the action requested
        if action == '@delete':
            # only admin
            return False
        if action == '@view':
            # QA user can modify any issues matching vendor_id
            if user.is_qa and self.fw._is_vendor(user):
                return True
            return False
        raise NotImplementedError('unknown security check action: %s:%s' % (self, action))

    def __repr__(self):
        return "Report object %s" % self.report_id

class Setting(db.Model):

    # sqlalchemy metadata
    __tablename__ = 'settings'
    __table_args__ = {'mysql_character_set': 'utf8mb4'}

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
    __table_args__ = {'mysql_character_set': 'utf8mb4'}

    datestr = Column(Integer, primary_key=True, unique=True, default=0, index=True)
    cnt = Column(Integer, default=1)

    def __init__(self, datestr=0, cnt=1):
        """ Constructor for object """
        self.cnt = cnt
        self.datestr = datestr

    def __repr__(self):
        return "Analytic object %s" % self.datestr

class AnalyticVendor(db.Model):

    # sqlalchemy metadata
    __tablename__ = 'analytics_vendor'
    __table_args__ = {'mysql_character_set': 'utf8mb4'}

    analytic_id = Column(Integer, primary_key=True, nullable=False, unique=True)
    datestr = Column(Integer, default=0, index=True)
    vendor_id = Column(Integer, ForeignKey('vendors.vendor_id'), nullable=False, index=True)
    cnt = Column(Integer, default=0)

    # link using foreign keys
    vendor = relationship('Vendor', foreign_keys=[vendor_id])

    def __init__(self, vendor_id, datestr=0, cnt=0):
        """ Constructor for object """
        self.vendor_id = vendor_id
        self.datestr = datestr
        self.cnt = cnt

    def __repr__(self):
        return "AnalyticVendor object %s:%s" % (self.datestr, self.vendor_id)

class AnalyticFirmware(db.Model):

    # sqlalchemy metadata
    __tablename__ = 'analytics_firmware'
    __table_args__ = {'mysql_character_set': 'utf8mb4'}

    analytic_id = Column(Integer, primary_key=True, nullable=False, unique=True)
    datestr = Column(Integer, default=0, index=True)
    firmware_id = Column(Integer, ForeignKey('firmware.firmware_id'), nullable=False, index=True)
    cnt = Column(Integer, default=0)

    # link using foreign keys
    firmware = relationship('Firmware', foreign_keys=[firmware_id])

    def __init__(self, firmware_id, datestr=0, cnt=0):
        """ Constructor for object """
        self.firmware_id = firmware_id
        self.datestr = datestr
        self.cnt = cnt

    def __repr__(self):
        return "AnalyticFirmware object %s:%s" % (self.datestr, self.firmware_id)

class UseragentKind(Enum):
    APP = 0
    FWUPD = 1
    LANG = 2
    DISTRO = 3

class Useragent(db.Model):

    # sqlalchemy metadata
    __tablename__ = 'useragents'
    __table_args__ = {'mysql_character_set': 'utf8mb4'}

    useragent_id = Column(Integer, primary_key=True, nullable=False, unique=True)
    kind = Column(Integer, default=0, index=True)
    datestr = Column(Integer, default=0)
    value = Column(Text, default=None)
    cnt = Column(Integer, default=1)

    def __init__(self, kind, value, datestr=0, cnt=1):
        """ Constructor for object """
        self.kind = kind.value
        self.value = value
        self.cnt = cnt
        self.datestr = datestr

    def __repr__(self):
        return "Useragent object %i:%s" % (self.kind, self.datestr)

class Protocol(db.Model):

    # sqlalchemy metadata
    __tablename__ = 'protocol'
    __table_args__ = {'mysql_character_set': 'utf8mb4'}

    protocol_id = Column(Integer, primary_key=True, nullable=False, unique=True)
    value = Column(Text, nullable=False)
    name = Column(Text, default=None)
    is_signed = Column(Boolean, default=False)
    is_public = Column(Boolean, default=False)
    can_verify = Column(Boolean, default=False)
    has_header = Column(Boolean, default=False)

    @property
    def security_claim(self):
        sc = SecurityClaim()
        if self.is_signed:
            sc.add_attr('success-signed-firmware', 'Update is cryptographically signed')
        else:
            sc.add_attr('warning-signed-firmware', 'Update is not cryptographically signed')
        if self.can_verify:
            sc.add_attr('success-verify-firmware', 'Firmware can be verified after flashing')
        else:
            sc.add_attr('warning-verify-firmware', 'Firmware cannot be verified after flashing')
        return sc

    def __init__(self, value, name=None, is_signed=False, can_verify=False, is_public=True, has_header=False):
        """ Constructor for object """
        self.value = value
        self.name = name
        self.is_signed = is_signed
        self.is_public = is_public
        self.can_verify = can_verify
        self.has_header = has_header

    def __repr__(self):
        return "Protocol object %s:%s" % (self.protocol_id, self.value)

class SearchEvent(db.Model):

    # sqlalchemy metadata
    __tablename__ = 'search_events'
    __table_args__ = {'mysql_character_set': 'utf8mb4'}

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
