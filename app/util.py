#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2015 Richard Hughes <richard@hughsie.com>
# Licensed under the GNU General Public License Version 2
#
# pylint: disable=wrong-import-position

import os
import json
import calendar
import datetime
import string
import random
import subprocess
import tempfile

from glob import fnmatch

from lxml import etree as ET
from flask import request, flash, render_template, g, Response

import gi
gi.require_version('GCab', '1.0')
from gi.repository import GCab
from gi.repository import GLib

def _fix_component_name(name, developer_name=None):
    if not name:
        return None

    # things just to nuke
    for nuke in ['(R)']:
        name = name.replace(nuke, '')

    words_new = []
    words_banned = ['firmware', 'update', 'system', 'device', 'bios', 'me',
                    'embedded', 'controller']
    if developer_name:
        words_banned.append(developer_name.lower())
    for word in name.split(' '):
        if not word:
            continue
        if word.lower() not in words_banned:
            words_new.append(word)
    return ' '.join(words_new)

def _is_hex(chunk):
    try:
        _ = int(chunk, 16)
    except ValueError as _:
        return False
    return True

def _validate_guid(guid):
    """ Validates if the string is a valid GUID """
    if not guid:
        return False
    if guid.lower() != guid:
        return False
    split = guid.split('-')
    if len(split) != 5:
        return False
    if len(split[0]) != 8 or not _is_hex(split[0]):
        return False
    if len(split[1]) != 4 or not _is_hex(split[1]):
        return False
    if len(split[2]) != 4 or not _is_hex(split[2]):
        return False
    if len(split[3]) != 4 or not _is_hex(split[3]):
        return False
    if len(split[4]) != 12 or not _is_hex(split[4]):
        return False
    return True

def _unwrap_xml_text(txt):
    txt = txt.replace('\r', '')
    new_lines = []
    for line in txt.split('\n'):
        if not line:
            continue
        new_lines.append(line.strip())
    return ' '.join(new_lines)

def _markdown_from_xml(markup):
    """ return MarkDown for the XML input """
    tmp = ''
    root = ET.fromstring('<description>' + markup + '</description>')
    for n in root:
        if n.tag == 'p':
            if n.text:
                tmp += _unwrap_xml_text(n.text) + '\n\n'
        elif n.tag == 'ul' or n.tag == 'ol':
            for c in n:
                if c.tag == 'li' and c.text:
                    tmp += ' * ' + _unwrap_xml_text(c.text) + '\n'
            tmp += '\n'
    tmp = tmp.strip(' \n')
    return tmp

def _check_is_markdown_li(line):
    if line.startswith('- '):
        return 2
    if line.startswith(' - '):
        return 3
    if line.startswith('* '):
        return 2
    if line.startswith(' * '):
        return 3
    if len(line) > 2 and line[0].isdigit() and line[1] == '.':
        return 2
    if len(line) > 3 and line[0].isdigit() and line[1].isdigit() and line[2] == '.':
        return 3
    return 0

def _xml_from_markdown(markdown):
    """ return a ElementTree for the markdown text """
    if not markdown:
        return None
    ul = None
    root = ET.Element('description')
    for line in markdown.split('\n'):
        line = line.strip()
        if not line:
            continue
        markdown_li_sz = _check_is_markdown_li(line)
        if markdown_li_sz:
            if ul is None:
                ul = ET.SubElement(root, 'ul')
            ET.SubElement(ul, 'li').text = line[markdown_li_sz:].strip()
        else:
            ul = None
            ET.SubElement(root, 'p').text = line
    return root

def _add_problem(problems, title, line=None):
    from app.models import Problem
    if line:
        tmp = "%s: [%s]" % (title, line)
    else:
        tmp = title
    for problem in problems:
        if problem.description == tmp:
            return
    problems.append(Problem('invalid-release-description', tmp))

def _check_both(problems, txt):
    if txt.isupper():
        _add_problem(problems, 'Uppercase only sentences are not allowed', txt)
    if txt.find('http://') != -1 or txt.find('https://') != -1:
        _add_problem(problems, 'Links cannot be included in update descriptions', txt)

def _check_is_fake_li(txt):
    for line in txt.split('\n'):
        if _check_is_markdown_li(line):
            return True
    return False

def _check_para(problems, txt):
    _check_both(problems, txt)
    if txt.startswith('[') and txt.endswith(']'):
        _add_problem(problems, 'Paragraphs cannot start and end with "[]"', txt)
    if txt.startswith('(') and txt.endswith(')'):
        _add_problem(problems, 'Paragraphs cannot start and end with "()"', txt)
    if _check_is_fake_li(txt):
        _add_problem(problems, 'Paragraphs cannot start with list elements', txt)
    if txt.find('.BLD') != -1 or txt.find('changes.new') != -1:
        _add_problem(problems, 'Do not refer to BLD or changes.new release notes', txt)
    if len(txt) > 300:
        _add_problem(problems, 'Paragraphs is too long, limit is 300 chars and was %i' % len(txt), txt)
    if len(txt) < 12:
        _add_problem(problems, 'Paragraphs is too short, minimum is 12 chars and was %i' % len(txt), txt)

def _check_li(problems, txt):
    _check_both(problems, txt)
    if txt in ('Nothing.', 'Not applicable.'):
        _add_problem(problems, 'List elements cannot be empty', txt)
    if _check_is_fake_li(txt):
        _add_problem(problems, 'List elements cannot start with bullets', txt)
    if txt.find('.BLD') != -1:
        _add_problem(problems, 'Do not refer to BLD release notes', txt)
    if txt.find('Fix the return code from GetHardwareVersion') != -1:
        _add_problem(problems, 'Do not use the example update notes!', txt)
    if len(txt) > 300:
        _add_problem(problems, 'List element is too long, limit is 300 chars and was %i' % len(txt), txt)
    if len(txt) < 5:
        _add_problem(problems, 'List element is too short, minimum is 5 chars and was %i' % len(txt), txt)

def _get_update_description_problems(root):
    problems = []
    n_para = 0
    n_li = 0
    for n in root:
        if n.tag == 'p':
            _check_para(problems, n.text)
            n_para += 1
        elif n.tag == 'ul' or n.tag == 'ol':
            for c in n:
                if c.tag == 'li':
                    _check_li(problems, c.text)
                    n_li += 1
                else:
                    _add_problem(problems, 'Invalid XML tag', '<%s>' % c.tag)
        else:
            _add_problem(problems, 'Invalid XML tag', '<%s>' % n.tag)
    if n_para > 5:
        _add_problem(problems, 'Too many paragraphs, limit is 5 and was %i' % n_para)
    if n_li > 20:
        _add_problem(problems, 'Too many list elements, limit is 20 and was %i' % n_li)
    if n_para < 1:
        _add_problem(problems, 'Not enough paragraphs, minimum is 1')
    return problems

def _get_settings(prefix=None):
    """ return a dict of all the settings """
    from app import db
    from .models import Setting
    settings = {}
    stmt = db.session.query(Setting)
    if prefix:
        stmt = stmt.filter(Setting.key.startswith(prefix))
    for setting in stmt.all():
        settings[setting.key] = setting.value
    return settings

def _get_absolute_path(fw):
    from app import app
    if fw.is_deleted:
        return os.path.join(app.config['RESTORE_DIR'], fw.filename)
    return os.path.join(app.config['DOWNLOAD_DIR'], fw.filename)

def _get_basename_safe(fn):
    """ gets the file basename, also with win32-style backslashes """
    return os.path.basename(fn.replace('\\', '/'))

def _get_dirname_safe(fn):
    """ gets the file dirname, also with win32-style backslashes """
    return os.path.dirname(fn.replace('\\', '/'))

def _archive_get_files_from_glob(arc, glob):
    arr = []
    for cffolder in arc.get_folders():
        for cffile in cffolder.get_files():
            filename = cffile.get_name().replace('\\', '/')
            if fnmatch.fnmatch(filename, glob):
                arr.append(cffile)
    return arr

def _archive_add(arc, filename, contents):
    cffile = GCab.File.new_with_bytes(filename, GLib.Bytes.new(contents))
    cffolders = arc.get_folders()
    if not cffolders:
        cffolders = [GCab.Folder.new(GCab.Compression.NONE)]
        arc.add_folder(cffolders[0])
    cffolders[0].add_file(cffile, False)

def _get_client_address():
    """ Gets user IP address """
    if request.headers.getlist("X-Forwarded-For"):
        return request.headers.getlist("X-Forwarded-For")[0]
    if not request.remote_addr:
        return '127.0.0.1'
    return request.remote_addr

def _event_log(msg, is_important=False):
    """ Adds an item to the event log """
    user_id = 2 	# Anonymous User
    vendor_id = 1	# admin
    request_path = None
    if hasattr(g, 'user') and g.user:
        user_id = g.user.user_id
        vendor_id = g.user.vendor_id
    if request:
        request_path = request.path
    from .models import Event
    from app import db
    event = Event(user_id=user_id,
                  message=msg,
                  vendor_id=vendor_id,
                  address=_get_client_address(),
                  request=request_path,
                  is_important=is_important)
    db.session.add(event)
    db.session.commit()

def _error_internal(msg=None, errcode=402):
    """ Error handler: Internal """
    flash("Internal error: %s" % msg, 'danger')
    return render_template('error.html'), errcode

def _error_permission_denied(msg=None):
    """ Error handler: Permission Denied """
    flash("Permission denied: %s" % msg, 'danger')
    return render_template('error.html'), 401

def _json_success(msg=None, uri=None, errcode=200):
    """ Success handler: JSON output """
    item = {}
    item['success'] = True
    if msg:
        item['msg'] = msg
    if uri:
        item['uri'] = uri
    dat = json.dumps(item, sort_keys=True, indent=4, separators=(',', ': '))
    return Response(response=dat,
                    status=errcode, \
                    mimetype="application/json")

def _json_error(msg=None, errcode=400):
    """ Error handler: JSON output """
    item = {}
    item['success'] = False
    if msg:
        item['msg'] = str(msg)
    dat = json.dumps(item, sort_keys=True, indent=4, separators=(',', ': '))
    return Response(response=dat,
                    status=errcode, \
                    mimetype="application/json")

def _get_chart_labels_months():
    """ Gets the chart labels """
    now = datetime.date.today()
    labels = []
    offset = 0
    for i in range(0, 12):
        if now.month - i == 0:
            offset = 1
        labels.append(calendar.month_name[now.month - i - offset])
    return labels

def _get_chart_labels_days(limit=30):
    """ Gets the chart labels """
    now = datetime.date.today()
    labels = []
    for i in range(0, limit):
        then = now - datetime.timedelta(i + 1)
        labels.append("%02i-%02i-%02i" % (then.year, then.month, then.day))
    return labels

def _get_chart_labels_hours():
    """ Gets the chart labels """
    labels = []
    for i in range(0, 24):
        labels.append("%02i" % i)
    return labels

def _email_check(value):
    """ Do a quick and dirty check on the email address """
    if len(value) < 5 or value.find('@') == -1 or value.find('.') == -1:
        return False
    return True

def _generate_password(size=10, chars=string.ascii_letters + string.digits):
    return ''.join(random.choice(chars) for _ in range(size))

def _get_certtool():
    from app import app
    return app.config['CERTTOOL'].split(' ')

def _pkcs7_certificate_info(text):

    # write certificate to temp file
    crt = tempfile.NamedTemporaryFile(mode='wb',
                                      prefix='pkcs7_',
                                      suffix=".p7b",
                                      dir=None,
                                      delete=True)
    crt.write(text.encode('utf8'))
    crt.flush()

    # get signature
    argv = _get_certtool() + ['--certificate-info', '--infile', crt.name]
    ps = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    out, err = ps.communicate()
    if ps.returncode != 0:
        raise IOError(err)
    info = {}
    for line in out.decode('utf8').split('\n'):
        try:
            key, value = line.strip().split(':', 2)
            if key == 'Serial Number (hex)':
                info['serial'] = value.strip()
        except ValueError as _:
            pass
    return info

def _pkcs7_signature_info(text, check_rc=True):

    # write signature to temp file
    sig = tempfile.NamedTemporaryFile(mode='wb',
                                      prefix='pkcs7_',
                                      suffix=".txt",
                                      dir=None,
                                      delete=True)
    sig.write(text.encode('utf8'))
    sig.flush()

    # parse
    argv = _get_certtool() + ['--p7-verify', '--infile', sig.name]
    ps = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    out, err = ps.communicate()
    if check_rc and ps.returncode != 0:
        raise IOError(out, err)
    info = {}
    for line in out.decode('utf8').split('\n'):
        try:
            key, value = line.strip().split(':', 2)
            if key == 'Signer\'s serial':
                info['serial'] = value.strip()
        except ValueError as _:
            pass
    return info

def _pkcs7_signature_verify(certificate, payload, signature):

    # check the signature against the client cert
    crt = tempfile.NamedTemporaryFile(mode='wb',
                                      prefix='pkcs7_',
                                      suffix=".p7b",
                                      dir=None,
                                      delete=True)
    crt.write(certificate.text.encode('utf8'))
    crt.flush()

    # write payload to temp file
    pay = tempfile.NamedTemporaryFile(mode='wb',
                                      prefix='pkcs7_',
                                      suffix=".json",
                                      dir=None,
                                      delete=True)
    pay.write(payload.encode('utf8'))
    pay.flush()

    # write signature to temp file
    sig = tempfile.NamedTemporaryFile(mode='wb',
                                      prefix='pkcs7_',
                                      suffix=".p7b",
                                      dir=None,
                                      delete=True)
    sig.write(signature.encode('utf8'))
    sig.flush()

    # verify
    status = None
    argv = _get_certtool() + ['--p7-verify',
                              '--load-certificate', crt.name,
                              '--infile', sig.name,
                              '--load-data', pay.name]
    ps = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    _, err = ps.communicate()
    if ps.returncode != 0:
        raise IOError(err)
    for line in err.decode('utf8').split('\n'):
        try:
            key, value = line.strip().split(':', 1)
            print(key, value)
            if key == 'Signature status':
                status = value.strip()
        except ValueError as _:
            pass
    return status == 'ok'
