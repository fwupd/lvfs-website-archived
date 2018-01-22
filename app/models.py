#!/usr/bin/python2
# -*- coding: utf-8 -*-
#
# Copyright (C) 2015-2017 Richard Hughes <richard@hughsie.com>
# Licensed under the GNU General Public License Version 2

#from app import db

class User(object):
    def __init__(self):
        """ Constructor for object """
        self.username = None
        self.password = None
        self.display_name = None
        self.email = None
        self.is_enabled = False
        self.is_qa = False
        self.group_id = None
        self.is_locked = False

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

class Group(object):
    def __init__(self):
        """ Constructor for object """
        self.group_id = None
        self.vendor_ids = []
    def __repr__(self):
        return "Group object %s" % self.group_id

class Vendor(object):
    def __init__(self):
        """ Constructor for object """
        self.group_id = None
        self.display_name = None
        self.plugins = None
        self.description = None
        self.visible = False
        self.is_fwupd_supported = None
        self.is_account_holder = None
        self.is_uploading = None
        self.comments = None
    def _get_sorting_key(self):
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

class EventLogItem(object):
    def __init__(self):
        """ Constructor for object """
        self.timestamp = None
        self.username = None
        self.group_id = None
        self.address = None
        self.message = None
        self.request = None
        self.is_important = False
    def __repr__(self):
        return "EventLogItem object %s" % self.message

class FirmwareRequirement(object):
    def __init__(self, kind=None, value=None, compare=None, version=None):
        """ Constructor for object """
        self.kind = kind        # e.g. 'id', 'firmware' or 'hardware'
        self.value = value      # e.g. 'bootloader' or 'org.freedesktop.fwupd'
        self.compare = compare
        self.version = version
    def to_string(self):
        return "%s/%s/%s/%s" % (self.kind, self.value, self.compare, self.version)
    def from_string(self, txt):
        tmp = txt.split('/')
        if len(tmp) != 4:
            return
        self.kind = tmp[0]
        self.value = tmp[1]
        self.compare = tmp[2]
        self.version = tmp[3]
    def __repr__(self):
        return "FirmwareRequirement object %s" % self.kind

class FirmwareMd(object):
    def __init__(self):
        """ Constructor for object """
        self.firmware_id = None    # this maps the object back into a Firmware
        self.cid = None
        self.guids = []
        self.version = None
        self.name = None
        self.summary = None
        self.checksum_contents = None
        self.release_description = None
        self.release_timestamp = 0
        self.developer_name = None
        self.metadata_license = None
        self.project_license = None
        self.url_homepage = None
        self.description = None
        self.checksum_container = None
        self.filename_contents = None
        self.release_installed_size = 0
        self.release_download_size = 0
        self.release_urgency = None
        self.screenshot_url = None
        self.screenshot_caption = None
        self.requirements = []
        self.metainfo_id = None

    def find_fwreq(self, kind=None, value=None):
        """ Find a FirmwareRequirement from the kind and/or value """
        for fwreq in self.requirements:
            if kind and fwreq.kind != kind:
                continue
            if value and fwreq.value != value:
                continue
            return fwreq
        return None

    def __repr__(self):
        return "FirmwareMd object %s" % self.firmware_id

class Firmware(object):
    def __init__(self):
        """ Constructor for object """
        self.group_id = None
        self.addr = None
        self.timestamp = None
        self.filename = None
        self.firmware_id = None
        self.target = None
        self.version_display = None
        self.mds = []
    def __repr__(self):
        return "Firmware object %s" % self.firmware_id

class Client(object):
    def __init__(self):
        """ Constructor for object """
        self.id = 0
        self.timestamp = None
        self.addr = None
        self.filename = None
        self.user_agent = None
    def __repr__(self):
        return "Client object %s" % self.id

class Report(object):
    def __init__(self):
        """ Constructor for object """
        self.id = 0
        self.timestamp = None
        self.state = None
        self.json = None
        self.machine_id = None
        self.firmware_id = None
        self.checksum = None
    def __repr__(self):
        return "Report object %s" % self.id

class DownloadKind(object):
    METADATA = 0
    FIRMWARE = 1
    SIGNING = 2
