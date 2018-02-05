#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# Copyright (C) 2015 Richard Hughes <richard@hughsie.com>
# Licensed under the GNU General Public License Version 2

from __future__ import print_function

import cgi
import datetime
import MySQLdb as mdb

from .models import User, FirmwareMd, Firmware, FirmwareRequirement, EventLogItem, Group, Vendor, Client, Report
from .hash import _addr_hash, _password_hash

def _create_user_item(e):
    """ Create a user object from the results """
    item = User()
    item.username = e[0]
    item.display_name = e[1]
    item.email = e[2]
    item.password = e[3]
    item.is_enabled = bool(e[4])
    item.is_qa = bool(e[5])
    item.group_id = e[6]
    item.is_locked = bool(e[7])
    item.is_analyst = bool(e[8])
    if item.username == 'admin':
        item.is_enabled = True
        item.is_qa = True
        item.is_locked = False
    return item

def _create_firmware_md(e):
    md = FirmwareMd()
    md.firmware_id = e[0]
    md.cid = e[1]
    md.guids = e[2].split(',')
    md.version = e[3]
    md.name = e[4]
    md.summary = e[5]
    md.checksum_contents = e[6]
    md.release_description = e[7]
    md.release_timestamp = e[8]
    md.developer_name = e[9]
    md.metadata_license = e[10]
    md.project_license = e[11]
    md.url_homepage = e[12]
    md.description = e[13]
    md.checksum_container = e[14]
    md.filename_contents = e[15]
    md.release_installed_size = e[16]
    md.release_download_size = e[17]
    md.release_urgency = e[18]
    md.screenshot_url = e[19]
    md.screenshot_caption = e[20]
    md.metainfo_id = e[21]
    if e[22]:
        for fwreq_str in e[22].split(','):
            fwreq = FirmwareRequirement()
            fwreq.from_string(fwreq_str)
            md.requirements.append(fwreq)
    return md

def _create_firmware_item(e):
    item = Firmware()
    item.group_id = e[0]
    item.addr = e[1]
    item.timestamp = e[2]
    item.filename = e[3]
    item.firmware_id = e[4]
    item.target = e[5]
    item.version_display = e[6]
    item.download_cnt = int(e[7])
    return item

def _create_client_item(e):
    item = Client()
    item.id = e[0]
    item.timestamp = e[1]
    item.addr = e[2]
    item.filename = e[3]
    item.user_agent = e[4]
    return item

def _create_report_item(e):
    item = Report()
    item.id = e[0]
    item.timestamp = e[1]
    item.state = e[2]
    item.json = e[3]
    item.machine_id = e[4]
    item.firmware_id = e[5]
    item.checksum = e[6]
    return item

def _create_vendor_item(e):
    item = Vendor()
    item.group_id = e[0]
    item.display_name = e[1]
    item.plugins = e[2]
    item.description = e[3]
    item.visible = int(e[4])
    item.is_fwupd_supported = e[5]
    item.is_account_holder = e[6]
    item.is_uploading = e[7]
    item.comments = e[8]
    return item

def _create_eventlog_item(e):
    item = EventLogItem()
    item.timestamp = e[0]
    item.username = e[1]
    item.group_id = e[2]
    item.address = e[3]
    item.message = e[4]
    item.is_important = e[5]
    item.request = e[6]
    return item

def _create_group_id(e):
    item = Group()
    item.group_id = e[0]
    if e[1]:
        item.vendor_ids = e[1].split(',')
    return item

def _get_datestr_from_datetime(when):
    return int("%04i%02i%02i" % (when.year, when.month, when.day))

class CursorError(Exception):
    def __init__(self, cur, e):
        if hasattr(cur, '_last_executed'):
            self.value = cgi.escape(cur._last_executed) + '&#10145; ' + cgi.escape(str(e))
        else:
            self.value = cgi.escape(str(e))
    def __str__(self):
        return repr(self.value)

class Database(object):

    def __init__(self, app):
        """ Constructor for object """
        self._db = None
        try:
            self._db = mdb.connect(app.config['DATABASE_HOST'],
                                   app.config['DATABASE_USERNAME'],
                                   app.config['DATABASE_PASSWORD'],
                                   app.config['DATABASE_DB'],
                                   int(app.config['DATABASE_PORT']),
                                   use_unicode=True, charset='utf8')
            self._db.autocommit(True)
        except mdb.Error as e:
            print("Error %d: %s" % (e.args[0], e.args[1]))
        assert self._db
        self.users = DatabaseUsers(self._db)
        self.groups = DatabaseGroups(self._db)
        self.eventlog = DatabaseEventlog(self._db)
        self.clients = DatabaseClients(self._db)
        self.firmware = DatabaseFirmware(self._db)
        self.vendors = DatabaseVendors(self._db)
        self.reports = DatabaseReports(self._db)
        self.settings = DatabaseSettings(self._db)

    def close(self):
        """ Clean up the database """
        if self._db:
            self._db.close()
            self._db = None

    def __del__(self):
        self.close()

    def cursor(self):
        return self._db.cursor()

class DatabaseGroups(object):

    def __init__(self, db):
        """ Constructor for object """
        self._db = db

    def add(self, group_id, vendor_ids=''):
        """ Adds the user to the userlist """
        assert group_id
        try:
            cur = self._db.cursor()
            cur.execute("INSERT INTO groups (group_id, vendor_ids) "
                        "VALUES (%s, %s);",
                        (group_id, ','.join(vendor_ids),))
        except mdb.Error as e:
            raise CursorError(cur, e)

    def remove(self, group_id):
        """ Removes the user from the userlist """
        assert group_id
        try:
            cur = self._db.cursor()
            cur.execute("DELETE FROM groups WHERE group_id=%s;", (group_id,))
        except mdb.Error as e:
            raise CursorError(cur, e)

    def set_property(self, group_id, key, value):
        """ Sets some properties on the user """
        assert group_id
        assert key
        cur = self._db.cursor()
        try:
            query = "UPDATE groups SET %s=%%s WHERE group_id=%%s;" % key
            cur.execute(query, (value, group_id,))
        except mdb.Error as e:
            raise CursorError(cur, e)

    def get_all(self):
        """ Get all the users """
        try:
            cur = self._db.cursor()
            cur.execute("SELECT group_id, vendor_ids FROM groups;")
        except mdb.Error as e:
            raise CursorError(cur, e)
        res = cur.fetchall()
        if not res:
            return []
        items = []
        for e in res:
            items.append(_create_group_id(e))
        return items

    def get_item(self, group_id):
        """ Gets information about a specific user """
        assert group_id
        try:
            cur = self._db.cursor()
            cur.execute("SELECT group_id, vendor_ids FROM groups "
                        "WHERE group_id = %s LIMIT 1;",
                        (group_id,))
        except mdb.Error as e:
            raise CursorError(cur, e)
        res = cur.fetchone()
        if not res:
            return None
        return _create_group_id(res)

class DatabaseUsers(object):

    def __init__(self, db):
        """ Constructor for object """
        self._db = db

    def get_signing_uid(self):
        """ Gets the signing UID for the site, i.e. the admin email address """
        try:
            cur = self._db.cursor()
            cur.execute("SELECT email FROM users WHERE username='admin'")
        except mdb.Error as e:
            raise CursorError(cur, e)
        key_uid = cur.fetchone()
        return key_uid[0]

    def add(self, username, password, name, email, group_id):
        """ Adds the user to the userlist """
        assert username
        assert password
        assert name
        assert email
        assert group_id
        pw_hash = _password_hash(password)
        try:
            cur = self._db.cursor()
            cur.execute("INSERT INTO users (username, password, display_name, "
                        "email, is_enabled, group_id) "
                        "VALUES (%s, %s, %s, %s, 1, %s);",
                        (username, pw_hash, name, email, group_id,))
        except mdb.Error as e:
            raise CursorError(cur, e)

    def remove(self, username):
        """ Removes the user from the userlist """
        assert username
        try:
            cur = self._db.cursor()
            cur.execute("DELETE FROM users WHERE username=%s;", (username,))
        except mdb.Error as e:
            raise CursorError(cur, e)

    def set_property(self, username, key, value):
        """ Sets some properties on the user """
        assert username
        assert key

        cur = self._db.cursor()
        try:
            query = "UPDATE users SET %s=%%s WHERE username=%%s;" % key
            if key == 'password':
                value = _password_hash(value)
            cur.execute(query, (value, username,))
        except mdb.Error as e:
            raise CursorError(cur, e)

    def is_enabled(self, username):
        """ Returns success if the username is present and enabled """
        assert username
        cur = self._db.cursor()
        try:
            cur.execute("SELECT is_enabled FROM users WHERE username=%s", (username,))
        except mdb.Error as e:
            raise CursorError(cur, e)
        auth = cur.fetchone()
        if auth:
            return True
        return False

    def verify(self, username, password):
        """ Verify that a username and password exists """
        assert username
        assert password
        pw_hash = _password_hash(password)
        try:
            cur = self._db.cursor()
            cur.execute("SELECT is_enabled FROM users WHERE username=%s AND password=%s;",
                        (username, pw_hash,))
        except mdb.Error as e:
            raise CursorError(cur, e)
        auth = cur.fetchone()
        if not auth:
            return False
        return True

    def update(self, username, password, name, email):
        """ Update user details """
        assert username
        assert password
        assert name
        assert email
        try:
            cur = self._db.cursor()
            cur.execute("UPDATE users SET display_name=%s, email=%s, password=%s "
                        "WHERE username=%s;",
                        (name, email, _password_hash(password), username,))
        except mdb.Error as e:
            raise CursorError(cur, e)

    def get_all(self):
        """ Get all the users """
        try:
            cur = self._db.cursor()
            cur.execute("SELECT username, display_name, email, password, "
                        "is_enabled, is_qa, group_id, is_locked, is_analyst FROM users;")
        except mdb.Error as e:
            raise CursorError(cur, e)
        res = cur.fetchall()
        if not res:
            return []
        items = []
        for e in res:
            items.append(_create_user_item(e))
        return items

    def get_item(self, username, password=None):
        """ Gets information about a specific user """
        assert username
        try:
            cur = self._db.cursor()
            if password:
                cur.execute("SELECT username, display_name, email, password, "
                            "is_enabled, is_qa, group_id, is_locked, is_analyst FROM users "
                            "WHERE username = %s AND password = %s LIMIT 1;",
                            (username, password,))
            else:
                cur.execute("SELECT username, display_name, email, password, "
                            "is_enabled, is_qa, group_id, is_locked, is_analyst FROM users "
                            "WHERE username = %s LIMIT 1;",
                            (username,))
        except mdb.Error as e:
            raise CursorError(cur, e)
        res = cur.fetchone()
        if not res:
            return None
        return _create_user_item(res)

class DatabaseFirmware(object):

    def __init__(self, db):
        """ Constructor for object """
        self._db = db

    def set_target(self, firmware_id, target):
        """ get the number of firmware files we've provided """
        assert firmware_id
        assert target
        try:
            cur = self._db.cursor()
            cur.execute("UPDATE firmware SET target=%s WHERE firmware_id=%s;", (target, firmware_id,))
        except mdb.Error as e:
            raise CursorError(cur, e)

    def set_download_count(self, firmware_id, cnt):
        """ set the download counter """
        assert firmware_id
        try:
            cur = self._db.cursor()
            cur.execute("UPDATE firmware SET download_cnt=%s WHERE firmware_id=%s;", (cnt, firmware_id,))
        except mdb.Error as e:
            raise CursorError(cur, e)

    def update(self, fw):
        """ Update firmware details """
        assert fw
        try:
            cur = self._db.cursor()
            cur.execute("UPDATE firmware SET version_display=%s "
                        "WHERE firmware_id=%s;",
                        (fw.version_display,
                         fw.firmware_id,))
            for md in fw.mds:
                req_str = []
                for fwreq in md.requirements:
                    req_str.append(fwreq.to_string())
                cur.execute("UPDATE firmware_md SET description=%s, "
                            "release_description=%s, "
                            "release_urgency=%s, "
                            "release_installed_size=%s, "
                            "release_download_size=%s, "
                            "requirements=%s "
                            "WHERE firmware_id=%s;",
                            (md.description,
                             md.release_description,
                             md.release_urgency,
                             md.release_installed_size,
                             md.release_download_size,
                             ','.join(req_str),
                             fw.firmware_id,))
        except mdb.Error as e:
            raise CursorError(cur, e)

    def add(self, fw):
        """ Add a firmware object to the database """
        try:
            cur = self._db.cursor()
            cur.execute("INSERT INTO firmware (group_id, addr, timestamp, "
                        "filename, firmware_id, target, version_display) "
                        "VALUES (%s, %s, CURRENT_TIMESTAMP, %s, %s, %s, %s);",
                        (fw.group_id,
                         fw.addr,
                         fw.filename,
                         fw.firmware_id,
                         fw.target,
                         fw.version_display,))
            for md in fw.mds:
                req_str = []
                for fwreq in md.requirements:
                    req_str.append(fwreq.to_string())
                cur.execute("INSERT INTO firmware_md (firmware_id, id, guid, version, "
                            "name, summary, checksum_contents, release_description, "
                            "release_timestamp, developer_name, metadata_license, "
                            "project_license, url_homepage, description, "
                            "checksum_container, filename_contents, "
                            "release_installed_size, "
                            "release_download_size, release_urgency, "
                            "screenshot_url, screenshot_caption, metainfo_id, "
                            "requirements) "
                            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, "
                            "%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);",
                            (fw.firmware_id,
                             md.cid,
                             ','.join(md.guids),
                             md.version,
                             md.name,
                             md.summary,
                             md.checksum_contents,
                             md.release_description,
                             md.release_timestamp,
                             md.developer_name,
                             md.metadata_license,
                             md.project_license,
                             md.url_homepage,
                             md.description,
                             md.checksum_container,
                             md.filename_contents,
                             md.release_installed_size,
                             md.release_download_size,
                             md.release_urgency,
                             md.screenshot_url,
                             md.screenshot_caption,
                             md.metainfo_id,
                             ','.join(req_str),))
        except mdb.Error as e:
            raise CursorError(cur, e)

    def remove(self, firmware_id):
        """ Removes firmware from the database if it exists """
        try:
            cur = self._db.cursor()
            cur.execute("DELETE FROM firmware WHERE firmware_id = %s;", (firmware_id,))
            cur.execute("DELETE FROM firmware_md WHERE firmware_id = %s;", (firmware_id,))
        except mdb.Error as e:
            raise CursorError(cur, e)

    def _add_items_md(self, item):
        try:
            cur = self._db.cursor()
            cur.execute("SELECT firmware_id, id, guid, version, "
                        "name, summary, checksum_contents, release_description, "
                        "release_timestamp, developer_name, metadata_license, "
                        "project_license, url_homepage, description, "
                        "checksum_container, filename_contents, "
                        "release_installed_size, release_download_size, "
                        "release_urgency, screenshot_url, screenshot_caption, "
                        "metainfo_id, requirements "
                        "FROM firmware_md WHERE firmware_id = %s ORDER BY guid DESC;",
                        (item.firmware_id,))
        except mdb.Error as e:
            raise CursorError(cur, e)
        res = cur.fetchall()
        if not res:
            return []
        for e in res:
            md = _create_firmware_md(e)
            item.mds.append(md)

    def get_all(self):
        """ Returns all firmware objects """
        try:
            cur = self._db.cursor()
            cur.execute("SELECT group_id, addr, timestamp, "
                        "filename, firmware_id, target, version_display, download_cnt "
                        "FROM firmware ORDER BY timestamp DESC;")
        except mdb.Error as e:
            raise CursorError(cur, e)
        res = cur.fetchall()
        if not res:
            return []
        fws = []
        for e in res:
            item = _create_firmware_item(e)
            fws.append(item)
            self._add_items_md(item)
        return fws

    def get_item(self, firmware_id):
        """ Gets a specific firmware object """
        try:
            cur = self._db.cursor()
            cur.execute("SELECT group_id, addr, timestamp, "
                        "filename, firmware_id, target, version_display, download_cnt "
                        "FROM firmware WHERE firmware_id = %s LIMIT 1;",
                        (firmware_id,))
        except mdb.Error as e:
            raise CursorError(cur, e)
        e = cur.fetchone()
        if not e:
            return None
        item = _create_firmware_item(e)
        self._add_items_md(item)
        return item

    def get_id_from_container_checksum(self, checksum_container):
        """ Gets a firmware ID from the container checksum """
        try:
            cur = self._db.cursor()
            cur.execute("SELECT firmware_id FROM firmware_md WHERE checksum_container = %s LIMIT 1;",
                        (checksum_container,))
        except mdb.Error as e:
            raise CursorError(cur, e)
        e = cur.fetchone()
        if not e:
            return None
        return e[0]


class DatabaseEventlog(object):

    def __init__(self, db):
        """ Constructor for object """
        self._db = db

    def add(self, msg, username, group_id, addr, is_important, request=None):
        """ Adds an item to the event log """
        assert msg
        assert username
        assert group_id
        assert addr
        try:
            cur = self._db.cursor()
            cur.execute("INSERT INTO event_log (username, group_id, addr, message, "
                        "is_important, request) "
                        "VALUES (%s, %s, %s, %s, %s, %s);",
                        (username, group_id, addr, msg, is_important, request))
        except mdb.Error as e:
            raise CursorError(cur, e)

    def size(self):
        """ Gets the length of the event log """
        try:
            cur = self._db.cursor()
            cur.execute("SELECT COUNT(timestamp) FROM event_log")
        except mdb.Error as e:
            raise CursorError(cur, e)
        res = cur.fetchone()[0]
        if not res:
            return 0
        return res

    def size_for_group_id(self, group_id):
        """ Gets the length of the event log """
        try:
            cur = self._db.cursor()
            cur.execute("SELECT COUNT(timestamp) FROM event_log "
                        "WHERE group_id = %s", (group_id,))
        except mdb.Error as e:
            raise CursorError(cur, e)
        res = cur.fetchone()[0]
        if not res:
            return 0
        return res

    def get_all(self, start, length):
        """ Gets the event log items """
        try:
            cur = self._db.cursor()
            cur.execute("SELECT timestamp, username, group_id, addr, message, "
                        "is_important, request "
                        "FROM event_log ORDER BY id DESC LIMIT %s,%s;",
                        (start, length,))
        except mdb.Error as e:
            raise CursorError(cur, e)
        res = cur.fetchall()
        if not res:
            return []
        items = []
        for e in res:
            items.append(_create_eventlog_item(e))
        return items

    def get_all_for_group_id(self, group_id, start, length):
        """ Gets the event log items """
        try:
            cur = self._db.cursor()
            cur.execute("SELECT timestamp, username, group_id, addr, message, "
                        "is_important, request "
                        "FROM event_log WHERE group_id = %s ORDER BY id DESC LIMIT %s,%s;",
                        (group_id, start, length,))
        except mdb.Error as e:
            raise CursorError(cur, e)
        res = cur.fetchall()
        if not res:
            return []
        items = []
        for e in res:
            items.append(_create_eventlog_item(e))
        return items

class DatabaseClients(object):

    def __init__(self, db):
        """ Constructor for object """
        self._db = db

    def add(self, when, kind):
        """ get the number of files we've provided """
        datestr = _get_datestr_from_datetime(when)
        try:
            cur = self._db.cursor()
            cur.execute("INSERT INTO analytics (datestr,kind) VALUES (%s, %s) "
                        "ON DUPLICATE KEY UPDATE cnt=cnt+1;",
                        (datestr, kind,))
        except mdb.Error as e:
            raise CursorError(cur, e)

    def get_firmware_count_filename(self, filename, age_days=0):
        """ get the number of files we've provided """
        try:
            cur = self._db.cursor()
            if age_days == 0:
                cur.execute("SELECT DISTINCT(COUNT(addr)) FROM clients "
                            "WHERE filename = %s", (filename,))
            else:
                cur.execute("SELECT DISTINCT(COUNT(addr)) FROM clients "
                            "WHERE filename = %s AND "
                            "TIMESTAMPDIFF(DAY, timestamp, CURRENT_TIMESTAMP()) < %s;",
                            (filename,age_days,))
        except mdb.Error as e:
            raise CursorError(cur, e)
        user_cnt = cur.fetchone()[0]
        if not user_cnt:
            return 0
        return user_cnt

    def get_user_agent_stats(self):
        """ Gets the number of user agents """
        try:
            cur = self._db.cursor()
            cur.execute("SELECT user_agent, COUNT(*) AS count FROM clients "
                        "WHERE user_agent IS NOT NULL "
                        "GROUP BY user_agent ORDER BY COUNT(*) DESC LIMIT 6;")
        except mdb.Error as e:
            raise CursorError(cur, e)
        res = cur.fetchall()
        if not res:
            return (["No data"], [0])
        labels = []
        data = []
        for e in res:
            # split up a generic agent to a specific client
            labels.append(str(e[0].split(' ')[0]))
            data.append(int(e[1]))
        return (labels, data)

    def increment(self, address, fn=None, user_agent=None):
        """ Adds a client address into the database """
        try:
            cur = self._db.cursor()
            cur.execute("INSERT INTO clients (addr, filename, user_agent) "
                        "VALUES (%s, %s, %s);",
                        (_addr_hash(address), fn, user_agent,))
            cur.execute("UPDATE firmware SET download_cnt = download_cnt + 1 "
                        "WHERE filename = %s;", (fn,))
        except mdb.Error as e:
            raise CursorError(cur, e)

    def get_stats_for_month(self, kind):
        """ Gets stats data for the last month """
        data = []
        now = datetime.date.today()

        cur = self._db.cursor()
        for i in range(30):
            datestr = _get_datestr_from_datetime(now)
            try:
                cur.execute("SELECT cnt FROM analytics "
                            "WHERE kind = %s AND datestr = %s",
                            (kind, datestr,))
            except mdb.Error as e:
                raise CursorError(cur, e)
            res = cur.fetchone()
            if res is None:
                data.append(0)
                continue
            data.append(int(res[0]))

            # back one day
            now -= datetime.timedelta(days=1)
        return data

    def get_stats_for_year(self, kind):
        """ Gets stats data for the last year """
        data = []
        now = datetime.date.today()

        cur = self._db.cursor()
        for i in range(12):
            datestrold = _get_datestr_from_datetime(now)
            now -= datetime.timedelta(days=30)
            datestrnew = _get_datestr_from_datetime(now)
            try:
                cur.execute("SELECT cnt FROM analytics WHERE kind = %s "
                            "AND datestr < %s AND datestr >= %s;",
                            (kind, datestrold, datestrnew,))
            except mdb.Error as e:
                raise CursorError(cur, e)
            res = cur.fetchall()
            if res is None:
                data.append(0)
                continue

            # sum up all the totals for each day in that month
            cnt = 0
            for res2 in res:
                cnt += res2[0]
            data.append(int(cnt))
        return data

    def get_stats_for_fn(self, size, interval, filename):
        """ Gets stats data """
        data = []
        now = datetime.date.today()

        # yes, there's probably a way to do this in one query with a
        # 30-level INNER JOIN or something clever...
        for i in range(size):
            start = now - datetime.timedelta((i * interval) + interval - 1)
            end = now - datetime.timedelta((i * interval) - 1)
            try:
                cur = self._db.cursor()
                cur.execute("SELECT COUNT(*) FROM clients "
                            "WHERE filename = %s AND timestamp >= %s "
                            "AND timestamp <  %s", (filename, start, end,))
            except mdb.Error as e:
                raise CursorError(cur, e)
            data.append(int(cur.fetchone()[0]))
        return data

    def get_all_for_filename(self, filename, limit=10):
        """ get the clients """
        try:
            cur = self._db.cursor()
            cur.execute("SELECT id, timestamp, addr, filename, user_agent FROM clients "
                        "WHERE filename = %s ORDER BY id DESC LIMIT %s",
                        (filename, limit,))
        except mdb.Error as e:
            raise CursorError(cur, e)
        items = []
        for e in cur.fetchall():
            items.append(_create_client_item(e))
        return items

    def get_all(self, limit=10):
        """ get the clients """
        try:
            cur = self._db.cursor()
            cur.execute("SELECT id, timestamp, addr, filename, user_agent FROM clients "
                        "ORDER BY id DESC LIMIT %s",
                        (limit,))
        except mdb.Error as e:
            raise CursorError(cur, e)
        items = []
        for e in cur.fetchall():
            items.append(_create_client_item(e))
        return items

class DatabaseReports(object):

    def __init__(self, db):
        """ Constructor for object """
        self._db = db

    def add(self, state, machine_id, firmware_id, checksum, json=None):
        """ add a report """
        try:
            cur = self._db.cursor()
            cur.execute("INSERT INTO reports (state, machine_id, firmware_id, checksum, json) "
                        "VALUES (%s, %s, %s, %s, %s)",
                        (state, machine_id, firmware_id, checksum, json,))
        except mdb.Error as e:
            raise CursorError(cur, e)

    def find_by_id_checksum(self, machine_id, checksum):
        """ get the reports """
        try:
            cur = self._db.cursor()
            cur.execute("SELECT id, timestamp, state, json, machine_id, firmware_id, checksum FROM reports "
                        "WHERE machine_id = %s AND checksum = %s LIMIT 1",
                        (machine_id, checksum,))
        except mdb.Error as e:
            raise CursorError(cur, e)
        res = cur.fetchone()
        if not res:
            return None
        return _create_report_item(res)

    def find_by_id(self, report_id):
        """ get the report """
        try:
            cur = self._db.cursor()
            cur.execute("SELECT id, timestamp, state, json, machine_id, firmware_id, checksum FROM reports "
                        "WHERE id = %s LIMIT 1",
                        (report_id,))
        except mdb.Error as e:
            raise CursorError(cur, e)
        res = cur.fetchone()
        if not res:
            return None
        return _create_report_item(res)

    def remove_by_id(self, report_id):
        """ Removes the report """
        assert report_id
        try:
            cur = self._db.cursor()
            cur.execute("DELETE FROM reports WHERE id=%s;", (report_id,))
        except mdb.Error as e:
            raise CursorError(cur, e)

    def get_all_for_firmware_id(self, firmware_id, limit=10, age=0):
        """ get the reports """
        try:
            cur = self._db.cursor()
            if age == 0:
                if limit > 0:
                    cur.execute("SELECT id, timestamp, state, json, machine_id, "
                                "firmware_id, checksum FROM reports "
                                "WHERE firmware_id = %s ORDER BY id DESC LIMIT %s",
                                (firmware_id, limit,))
                else:
                    cur.execute("SELECT id, timestamp, state, json, machine_id, "
                                "firmware_id, checksum FROM reports "
                                "WHERE firmware_id = %s ORDER BY id DESC",
                                (firmware_id,))
            else:
                if limit > 0:
                    cur.execute("SELECT id, timestamp, state, json, machine_id, "
                                "firmware_id, checksum FROM reports "
                                "WHERE firmware_id = %s AND "
                                "TIMESTAMPDIFF(DAY, timestamp, CURRENT_TIMESTAMP()) < %s "
                                "ORDER BY id DESC LIMIT %s",
                                (firmware_id, age, limit,))
                else:
                    cur.execute("SELECT id, timestamp, state, json, machine_id, "
                                "firmware_id, checksum FROM reports "
                                "WHERE firmware_id = %s AND "
                                "TIMESTAMPDIFF(DAY, timestamp, CURRENT_TIMESTAMP()) < %s "
                                "ORDER BY id DESC",
                                (firmware_id, age,))
        except mdb.Error as e:
            raise CursorError(cur, e)
        items = []
        for e in cur.fetchall():
            items.append(_create_report_item(e))
        return items

    def get_all(self, limit=10):
        """ get the reports """
        try:
            cur = self._db.cursor()
            cur.execute("SELECT id, timestamp, state, json, machine_id, firmware_id, checksum FROM reports "
                        "ORDER BY id DESC LIMIT %s",
                        (limit,))
        except mdb.Error as e:
            raise CursorError(cur, e)
        items = []
        for e in cur.fetchall():
            items.append(_create_report_item(e))
        return items

class DatabaseVendors(object):

    def __init__(self, db):
        """ Constructor for object """
        self._db = db

    def add(self, group_id):
        """ Adds the vendor to the vendorlist """
        assert group_id
        try:
            cur = self._db.cursor()
            cur.execute("INSERT INTO vendors (group_id) VALUES (%s);",
                        (group_id,))
        except mdb.Error as e:
            raise CursorError(cur, e)

    def remove(self, group_id):
        """ Removes the vendor from the vendorlist """
        assert group_id
        try:
            cur = self._db.cursor()
            cur.execute("DELETE FROM vendors WHERE group_id=%s;", (group_id,))
        except mdb.Error as e:
            raise CursorError(cur, e)

    def modify(self, group_id, display_name, plugins, description, visible, is_fwupd_supported, is_account_holder, is_uploading, comments):
        """ Update vendor details """
        assert group_id
        assert display_name
        assert description
        try:
            cur = self._db.cursor()
            cur.execute("UPDATE vendors SET display_name=%s, plugins=%s, "
                        "description=%s, visible=%s, is_fwupd_supported=%s, "
                        "is_account_holder=%s, is_uploading=%s, comments=%s "
                        "WHERE group_id=%s;",
                        (display_name, plugins, description, visible,
                         is_fwupd_supported, is_account_holder, is_uploading,
                         comments, group_id,))
        except mdb.Error as e:
            raise CursorError(cur, e)

    def get_all(self):
        """ Get all the vendors """
        try:
            cur = self._db.cursor()
            cur.execute("SELECT group_id, display_name, plugins, description, "
                        "visible, is_fwupd_supported, is_account_holder, "
                        "is_uploading, comments FROM vendors;")
        except mdb.Error as e:
            raise CursorError(cur, e)
        res = cur.fetchall()
        if not res:
            return []
        items = []
        for e in res:
            items.append(_create_vendor_item(e))
        return items

    def get_item(self, group_id):
        """ Gets information about a specific vendor """
        assert group_id
        try:
            cur = self._db.cursor()
            cur.execute("SELECT group_id, display_name, plugins, description, "
                        "visible, is_fwupd_supported, is_account_holder, "
                        "is_uploading, comments FROM vendors "
                        "WHERE group_id = %s LIMIT 1;",
                        (group_id,))
        except mdb.Error as e:
            raise CursorError(cur, e)
        res = cur.fetchone()
        if not res:
            return None
        return _create_vendor_item(res)

class DatabaseSettings(object):

    def __init__(self, db):
        """ Constructor for object """
        self._db = db

    def add(self, key, value):
        """ Update vendor details """
        assert key
        try:
            cur = self._db.cursor()
            cur.execute("INSERT INTO settings (config_key, config_value) "
                        "VALUES (%s, %s);",
                        (key, value,))
        except mdb.Error as e:
            raise CursorError(cur, e)

    def modify(self, key, value):
        """ Update setting """
        assert key
        try:
            cur = self._db.cursor()
            cur.execute("UPDATE settings SET config_value=%s WHERE config_key=%s;", (value, key,))
        except mdb.Error as e:
            raise CursorError(cur, e)

    def get_all(self):
        """ Get all the settings """
        try:
            cur = self._db.cursor()
            cur.execute("SELECT config_key, config_value FROM settings;")
        except mdb.Error as e:
            raise CursorError(cur, e)
        res = cur.fetchall()
        if not res:
            return []
        settings = {}
        for e in res:
            settings[e[0]] = e[1]
        return settings

    def get_filtered(self, prefix):
        settings_filtered = {}
        settings = self.get_all()
        for key in settings:
            if not key.startswith(prefix):
                continue
            settings_filtered[key[len(prefix):]] = settings[key]
        return settings_filtered
