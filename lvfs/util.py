#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2015 Richard Hughes <richard@hughsie.com>
#
# SPDX-License-Identifier: GPL-2.0+
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

from functools import wraps

from lxml import etree as ET
from flask import request, flash, render_template, g, Response, redirect, url_for

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

def _markdown_from_root(root):
    """ return MarkDown for the XML input """
    tmp = ''
    for n in root:
        if n.tag == 'p':
            if list(n):
                raise KeyError('Invalid XML, found child of {}'.format(n.tag))
            if n.text:
                tmp += _unwrap_xml_text(n.text) + '\n\n'
        elif n.tag == 'ul' or n.tag == 'ol':
            for c in n:
                if c.tag == 'li':
                    if list(c):
                        raise KeyError('Invalid XML, found child of {}'.format(c.tag))
                    if c.text:
                        tmp += ' * ' + _unwrap_xml_text(c.text) + '\n'
                else:
                    raise KeyError('Invalid XML, got {}'.format(c.tag))
            tmp += '\n'
        else:
            raise KeyError('Invalid XML, got {}'.format(n.tag))
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

def _add_problem(problems, description, line=None):
    from lvfs.models import Claim
    for problem in problems:
        if problem.description.split('\n')[0] == description:
            return
    if line:
        description += '\n{}'.format(line)
    problems.append(Claim(kind='invalid-release-description',
                          icon='warning',
                          summary='Invalid release description',
                          description=description))

def _check_both(problems, txt):
    if txt.isupper():
        _add_problem(problems, 'Uppercase only sentences are not allowed', txt)
    if txt.find('http://') != -1 or txt.find('https://') != -1:
        _add_problem(problems, 'Links cannot be included in update descriptions', txt)
    if txt.find('CVE-') != -1:
        _add_problem(problems, 'CVEs in update description')
    if txt.find('LEN-') != -1:
        _add_problem(problems, 'Lenovo-specific security advisory tag in update description')
    if txt.find('DSA-') != -1:
        _add_problem(problems, 'Dell-specific security advisory tag in update description')
    if txt.find('INTEL-SA-') != -1:
        _add_problem(problems, 'Intel-specific security advisory tag in update description')
    if txt.find('INTEL-TA-') != -1:
        _add_problem(problems, 'Intel-specific technical advisory tag in update description')
    if txt.find('REMOVE_ME') != -1:
        _add_problem(problems, 'Update description should be checked after auto-importing issues')

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
        _add_problem(problems, 'Paragraph too long, limit is 300 chars and was %i' % len(txt), txt)
    if len(txt) < 12:
        _add_problem(problems, 'Paragraph too short, minimum is 12 chars and was %i' % len(txt), txt)

def _check_li(problems, txt):
    _check_both(problems, txt)
    if txt in ('Nothing.', 'Not applicable.'):
        _add_problem(problems, 'List element cannot be empty', txt)
    if _check_is_fake_li(txt):
        _add_problem(problems, 'List element cannot start with bullets', txt)
    if txt.find('.BLD') != -1:
        _add_problem(problems, 'Do not refer to BLD notes', txt)
    if txt.find('Fix the return code from GetHardwareVersion') != -1:
        _add_problem(problems, 'Do not use the example update notes!', txt)
    if len(txt) > 300:
        _add_problem(problems, 'List element too long, limit is 300 chars and was %i' % len(txt), txt)
    if len(txt) < 5:
        _add_problem(problems, 'List element too short, minimum is 5 chars and was %i' % len(txt), txt)

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
    from lvfs import db
    from lvfs.models import Setting
    settings = {}
    stmt = db.session.query(Setting)
    if prefix:
        stmt = stmt.filter(Setting.key.startswith(prefix))
    for setting in stmt:
        settings[setting.key] = setting.value
    return settings

def _get_absolute_path(fw):
    from lvfs import app
    if fw.is_deleted:
        return os.path.join(app.config['RESTORE_DIR'], fw.filename)
    return os.path.join(app.config['DOWNLOAD_DIR'], fw.filename)

def _get_sanitized_basename(basename):
    basename_sane = basename.encode('ascii', 'ignore').decode('utf-8')
    for key, value in [(',', '_')]:
        basename_sane = basename_sane.replace(key, value)
    return basename_sane

def _get_shard_path(shard):
    from lvfs import app
    return os.path.join(app.config['SHARD_DIR'], str(shard.component_id), shard.name)

def _get_client_address():
    """ Gets user IP address """
    try:
        if request.headers.getlist("X-Forwarded-For"):
            return request.headers.getlist("X-Forwarded-For")[0]
        if not request.remote_addr:
            return '127.0.0.1'
        return request.remote_addr
    except RuntimeError as _:
        return '127.0.0.1'

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
    from lvfs.models import Event
    from lvfs import db
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

def _get_chart_labels_months(ts=1):
    """ Gets the chart labels """
    now = datetime.date.today()
    labels = []
    for i in range(0, 12 * ts):
        then = now - datetime.timedelta((i + 1) * 30)
        labels.append('{} {}'.format(calendar.month_name[then.month], then.year))
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
    from lvfs import app
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

def admin_login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not g.user.check_acl('@admin'):
            flash('Only the admin team can access this resource', 'danger')
            return redirect(url_for('main.route_dashboard'))
        return f(*args, **kwargs)
    return decorated_function
