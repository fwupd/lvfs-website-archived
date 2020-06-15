#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2015-2018 Richard Hughes <richard@hughsie.com>
#
# SPDX-License-Identifier: GPL-2.0+
#
# pylint: disable=too-many-locals,too-many-statements,too-few-public-methods

import gzip
import hashlib
import os
import random
import uuid

from sqlalchemy import func

def _execute_count_star(q):
    count_query = q.statement.with_only_columns([func.count()]).order_by(None)
    return q.session.execute(count_query).scalar()

def _make_boring(val):
    out = ''
    for v in val.lower():
        if 'a' <= v <= 'z':
            out += v
        elif v == ' ' and not out.endswith('_'):
            out += '_'
    for suffix in ['_company',
                   '_corporation',
                   '_enterprises',
                   '_incorporated',
                   '_industries',
                   '_international',
                   '_limited',
                   '_services',
                   '_studios',
                   '_inc']:
        out = out.replace(suffix, '')
    return out

def _should_anonymize(v):
    if v.group_id == 'hughski': # this is my hobby; I have no secrets
        return False
    return True

def _make_fake_ip_address():
    return '%i.%i.%i.%i' % (random.randint(1, 254),
                            random.randint(1, 254),
                            random.randint(1, 254),
                            random.randint(1, 254))

def _make_fake_version():
    return '%i.%i.%i' % (random.randint(0, 1),
                         random.randint(1, 16),
                         random.randint(1, 254))

def anonymize_db(db):
    from .models import Vendor, Firmware

    # get vendor display names
    vendor_names = []
    with gzip.open('data/vendors.txt.gz', 'rb') as f:
        for ln in f.read().decode().split('\n'):
            if not ln:
                continue
            vendor_names.append(ln)
    random.shuffle(vendor_names)

    # get some plausible user names
    user_names = []
    with gzip.open('data/users.txt.gz', 'rb') as f:
        for ln in f.read().decode().split('\n'):
            if not ln:
                continue
            user_names.append(ln)
    random.shuffle(user_names)

    # get some plausible device names
    device_names = []
    with gzip.open('data/devices.txt.gz', 'rb') as f:
        for ln in f.read().decode().split('\n'):
            if not ln:
                continue
            device_names.append(ln)
    random.shuffle(device_names)

    # get some random words for keywords
    generic_words = []
    with open('/usr/share/dict/words', 'rb') as f:
        for ln in f.read().decode().split('\n'):
            if not ln:
                continue
            generic_words.append(ln)
    random.shuffle(generic_words)

    # anonymize vendors
    idx_generic_words = 0
    idx_user_names = 0
    idx_vendor_names = 0
    for v in db.session.query(Vendor):
        if not _should_anonymize(v):
            continue
        v.display_name = vendor_names[idx_vendor_names]
        v.group_id = _make_boring(v.display_name)
        v.description = 'Vendor has not released an official statement'
        v.comments = 'We pass no judgement'
        v.icon = 'vendor-1.png'
        v.keywords = generic_words[idx_generic_words]
        v.plugins = 'generichid >= 0.9.9'
        v.oauth_unknown_user = None
        v.oauth_domain_glob = None
        v.username_glob = '*@' + v.group_id.replace('_', '') + '.com'
        v.remote.name = 'embargo-' + v.group_id
        idx_generic_words += 1

        # anonymize restrictions
        for r in v.restrictions:
            r.value = 'USB:0x0123'

        # anonymize users
        for u in v.users:
            if u.username == 'sign-test@fwupd.org':
                continue
            u.display_name = user_names[idx_user_names]
            u.username = _make_boring(u.display_name) + u.vendor.username_glob[1:]
            idx_user_names += 1
            for crt in u.certificates:
                crt.serial = 'deadbeefdeadbeefdeadbeefdeadbeefdeadbeef'
                crt.text = '-----BEGIN CERTIFICATE-----\nFUBAR\n-----END CERTIFICATE-----'
        idx_vendor_names += 1

    # anonymize firmware
    idx_device_names = 0
    device_names_existing = {}
    for fw in db.session.query(Firmware):
        if not _should_anonymize(fw.vendor):
            continue
        for md in fw.mds:
            md.checksum_contents_sha1 = hashlib.sha1(os.urandom(32)).hexdigest()
            md.checksum_contents_sha256 = hashlib.sha256(os.urandom(32)).hexdigest()
            for csum in md.device_checksums:
                csum.kind = 'SHA1'
                csum.value = hashlib.sha1(os.urandom(32)).hexdigest()
            if md.name not in device_names_existing:
                device_names_existing[md.name] = device_names[idx_device_names]
                idx_device_names += 1
            md.name = device_names_existing[md.name]
            md.summary = 'Firmware for the ' + md.name
            md.description = None
            md.source_url = None
            md.release_description = 'This fixes some bugs'
            md.url_homepage = 'https://www.' + fw.vendor.username_glob[2:]
            md.details_url = 'https://www.' + fw.vendor.username_glob[2:]
            md.developer_name = fw.vendor.display_name
            md.filename_contents = 'firmware.bin'
            md.release_timestamp = 0
            md.version = _make_fake_version()
            md.release_installed_size = random.randint(100000, 1000000)
            md.release_download_size = random.randint(200000, 1000000)
            md.screenshot_url = None
            md.screenshot_caption = None
            md.appstream_id = 'com.' + fw.vendor.group_id + '.' + \
                              _make_boring(md.name) + '.firmware'
            for gu in md.guids:
                gu.value = str(uuid.uuid4())
            for kw in md.keywords:
                kw.value = generic_words[idx_generic_words]
                idx_generic_words += 1

        # components now changed
        fw.addr = _make_fake_ip_address()
        fw.checksum_upload_sha1 = hashlib.sha1(os.urandom(4096)).hexdigest()
        fw.checksum_upload_sha256 = hashlib.sha256(os.urandom(4096)).hexdigest()
        fw.checksum_signed_sha1 = hashlib.sha1(os.urandom(4096)).hexdigest()
        fw.checksum_signed_sha256 = hashlib.sha256(os.urandom(4096)).hexdigest()
        fw.filename = fw.checksum_upload_sha256 + '-' + fw.vendor.group_id + '-' + \
                      _make_boring(fw.md_prio.name) + '-' + fw.version_display + '.cab'

    # phew!
    db.session.commit()

def init_db(db):

    # ensure all tables exist
    db.metadata.create_all(bind=db.engine)

    # ensure admin user exists
    from .models import User, UserAction, Vendor, Remote, Verfmt, Protocol, Category
    from .hash import _otp_hash
    if not db.session.query(Remote).filter(Remote.name == 'stable').first():
        db.session.add(Remote(name='stable', is_public=True))
        db.session.add(Remote(name='testing', is_public=True))
        db.session.add(Remote(name='private'))
        db.session.add(Remote(name='deleted'))
        db.session.commit()
    if not db.session.query(Verfmt).filter(Verfmt.value == 'triplet').first():
        db.session.add(Verfmt(value='quad'))
        db.session.add(Verfmt(value='triplet'))
        db.session.commit()
    if not db.session.query(Protocol).filter(Protocol.value == 'com.hughski.colorhug').first():
        db.session.add(Protocol(value='com.hughski.colorhug', is_public=True))
        db.session.add(Protocol(value='org.usb.dfu', is_public=True))
        db.session.add(Protocol(value='org.uefi.capsule', is_public=True))
        db.session.commit()
    if not db.session.query(Category).filter(Category.value == 'triplet').first():
        db.session.add(Category(value='X-Device'))
        db.session.add(Category(value='X-ManagementEngine'))
        db.session.commit()
    if not db.session.query(User).filter(User.username == 'sign-test@fwupd.org').first():
        remote = Remote(name='embargo-admin')
        db.session.add(remote)
        db.session.commit()
        vendor = Vendor(group_id='admin')
        vendor.display_name = 'Acme Corp.'
        vendor.description = 'A fake vendor used for testing firmware'
        vendor.remote_id = remote.remote_id
        db.session.add(vendor)
        db.session.commit()
        u = User(username='sign-test@fwupd.org',
                 auth_type='local',
                 otp_secret=_otp_hash(),
                 display_name='Admin User',
                 vendor_id=vendor.vendor_id)
        u.actions.append(UserAction(value='admin'))
        u.actions.append(UserAction(value='qa'))
        u.actions.append(UserAction(value='analyst'))
        u.actions.append(UserAction(value='notify-server-error'))
        u.password = "Pa$$w0rd"
        db.session.add(u)
        db.session.commit()
    if not db.session.query(User).filter(User.username == 'anon@fwupd.org').first():
        db.session.add(User(username='anon@fwupd.org',
                            display_name='Anonymous User',
                            vendor_id=1))
        db.session.commit()

def drop_db(db):
    db.metadata.drop_all(bind=db.engine)
