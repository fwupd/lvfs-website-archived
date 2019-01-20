#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# Copyright (C) 2015-2018 Richard Hughes <richard@hughsie.com>
# Licensed under the GNU General Public License Version 2
#
# pylint: disable=too-many-locals,too-many-statements,too-few-public-methods

from __future__ import print_function

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
        if v >= 'a' and v <= 'z':
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
    if v.group_id == 'admin':
        return False
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
    from .models import Vendor, Firmware, Client

    # get vendor display names
    vendor_names = []
    with gzip.open('data/vendors.txt.gz', 'rb') as f:
        for ln in f.read().split('\n'):
            if not ln:
                continue
            vendor_names.append(ln.decode('utf-8'))
    random.shuffle(vendor_names)

    # get some plausible user names
    user_names = []
    with gzip.open('data/users.txt.gz', 'rb') as f:
        for ln in f.read().split('\n'):
            if not ln:
                continue
            user_names.append(ln.decode('utf-8'))
    random.shuffle(user_names)

    # get some plausible device names
    device_names = []
    with gzip.open('data/devices.txt.gz', 'rb') as f:
        for ln in f.read().split('\n'):
            if not ln:
                continue
            device_names.append(ln.decode('utf-8'))
    random.shuffle(device_names)

    # get some random words for keywords
    f = open('/usr/share/dict/words', 'r')
    generic_words = []
    for ln in f.read().split('\n'):
        if not ln:
            continue
        generic_words.append(ln.decode('utf-8'))
    random.shuffle(generic_words)

    # anonymize vendors
    idx_generic_words = 0
    idx_user_names = 0
    idx_vendor_names = 0
    for v in db.session.query(Vendor).all():
        if not _should_anonymize(v):
            continue
        v.display_name = vendor_names[idx_vendor_names]
        v.group_id = _make_boring(v.display_name)
        v.description = u'Vendor has not released an official statement'
        v.comments = u'We pass no judgement'
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
            u.display_name = user_names[idx_user_names]
            u.username = _make_boring(u.display_name) + u.vendor.username_glob[1:]
            idx_user_names += 1
        idx_vendor_names += 1

    # anonymize firmware
    idx_device_names = 0
    device_names_existing = {}
    for fw in db.session.query(Firmware).all():
        if not _should_anonymize(fw.vendor):
            continue
        for md in fw.mds:
            md.checksum_contents = hashlib.sha1(os.urandom(32)).hexdigest()
            for csum in md.device_checksums:
                csum.kind = 'SHA1'
                csum.value = hashlib.sha1(os.urandom(32)).hexdigest()
            if md.name not in device_names_existing:
                device_names_existing[md.name] = device_names[idx_device_names]
                idx_device_names += 1
            md.name = device_names_existing[md.name]
            md.summary = 'Firmware for the ' + md.name
            md.description = None
            md.release_description = 'This fixes some bugs'
            md.url_homepage = 'https://www.' + fw.vendor.username_glob[2:]
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
        fw.checksum_upload = hashlib.sha1(os.urandom(32)).hexdigest()
        fw.checksum_signed = hashlib.sha1(os.urandom(32)).hexdigest()
        fw.filename = fw.checksum_upload + '-' + fw.vendor.group_id + '-' + \
                      _make_boring(fw.mds[0].name) + '-' + fw.version_display + '.cab'

    # anonymize clients -- only do this on beefy hardware...
    if 'FLASK_RANDOMIZE_CLIENTS' in os.environ:
        for cl in db.session.query(Client).all():
            cl.addr = hashlib.sha1(os.urandom(32)).hexdigest()

    # phew!
    db.session.commit()

def init_db(db):

    # ensure all tables exist
    db.metadata.create_all(bind=db.engine)

    # ensure admin user exists
    from .models import User, Vendor, Remote
    if not db.session.query(Remote).filter(Remote.name == 'stable').first():
        db.session.add(Remote(name='stable', is_public=True))
        db.session.add(Remote(name='testing', is_public=True))
        db.session.add(Remote(name='private'))
        db.session.add(Remote(name='deleted'))
        db.session.commit()
    if not db.session.query(User).filter(User.username == 'admin').first():
        remote = Remote(name='embargo-admin')
        db.session.add(remote)
        db.session.commit()
        vendor = Vendor('admin')
        vendor.display_name = u'Acme Corp.'
        vendor.description = u'A fake vendor used for testing firmware'
        vendor.is_account_holder = 'yes'
        vendor.remote_id = remote.remote_id
        db.session.add(vendor)
        db.session.commit()
        db.session.add(User(username='sign-test@fwupd.org',
                            password_hash=u'5459dbe5e9aa80e077bfa40f3fb2ca8368ed09b4',
                            auth_type='local',
                            display_name=u'Admin User',
                            vendor_id=vendor.vendor_id,
                            is_admin=True,
                            is_qa=True,
                            is_analyst=True))
        db.session.commit()
    if not db.session.query(User).filter(User.username == 'anonymous').first():
        db.session.add(User(username='anonymous@fwupd.org',
                            display_name=u'Anonymous User',
                            vendor_id=1))
        db.session.commit()

def drop_db(db):
    db.metadata.drop_all(bind=db.engine)
