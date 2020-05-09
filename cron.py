#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2015-2018 Richard Hughes <richard@hughsie.com>
#
# SPDX-License-Identifier: GPL-2.0+
#
# pylint: disable=singleton-comparison,wrong-import-position,too-many-nested-blocks

import os
import sys
import glob
import difflib
import hashlib
import datetime

from collections import defaultdict

import yara

from lxml import etree as ET

from flask import render_template, g

from cabarchive import CabArchive, CabFile
from jcat import JcatFile, JcatBlobSha1, JcatBlobSha256, JcatBlobKind

from lvfs import app, db, ploader
from lvfs.dbutils import _execute_count_star
from lvfs.emails import send_email
from lvfs.firmware.utils import _firmware_delete
from lvfs.models import Remote, Firmware, Vendor, Client, AnalyticVendor, User, YaraQuery, YaraQueryResult
from lvfs.models import AnalyticFirmware, Useragent, UseragentKind, Analytic, Report, Metric
from lvfs.models import ComponentShard, ComponentShardInfo, Test, Component, Category, Protocol, FirmwareEvent
from lvfs.models import _get_datestr_from_datetime
from lvfs.metadata.utils import _metadata_update_targets, _metadata_update_pulp, _generate_metadata_mds
from lvfs.util import _event_log, _get_shard_path, _get_absolute_path
from lvfs.upload.uploadedfile import UploadedFile, MetadataInvalid

def _regenerate_and_sign_metadata(only_embargo=False):

    # get list of dirty remotes
    remotes = []
    for r in db.session.query(Remote):
        if not r.is_signed:
            continue
        # fix up any remotes that are not dirty, but have firmware that is dirty
        # -- which shouldn't happen, but did...
        if not r.is_dirty:
            for fw in r.fws:
                if not fw.is_dirty:
                    continue
                print('Marking remote %s as dirty due to %u' % (r.name, fw.firmware_id))
                r.is_dirty = True
        if r.is_dirty:
            if r.is_public and only_embargo:
                continue
            remotes.append(r)

    # nothing to do
    if not remotes:
        return

    # set destination path from app config
    download_dir = app.config['DOWNLOAD_DIR']
    if not os.path.exists(download_dir):
        os.mkdir(download_dir)

    # update everything required
    invalid_fns = []
    for r in remotes:
        print('Updating: %s' % r.name)
    for r, blob_xmlgz in _metadata_update_targets(remotes):

        # write metadata-?????.xml.gz
        fn_xmlgz = os.path.join(download_dir, r.filename)
        with open(fn_xmlgz, 'wb') as f:
            f.write(blob_xmlgz)
        invalid_fns.append(fn_xmlgz)

        # write metadata.xml.gz
        fn_xmlgz = os.path.join(download_dir, r.filename_newest)
        with open(fn_xmlgz, 'wb') as f:
            f.write(blob_xmlgz)
        invalid_fns.append(fn_xmlgz)

        # create Jcat item with SHA256 checksum blob
        jcatfile = JcatFile()
        jcatitem = jcatfile.get_item(r.filename)
        jcatitem.add_alias_id(r.filename_newest)
        jcatitem.add_blob(JcatBlobSha1(blob_xmlgz))
        jcatitem.add_blob(JcatBlobSha256(blob_xmlgz))

        # write each signed file
        for blob in ploader.metadata_sign(blob_xmlgz):

            # add GPG only to archive for backwards compat with older fwupd
            if blob.kind == JcatBlobKind.GPG:
                fn_xmlgz_asc = fn_xmlgz + '.' + blob.filename_ext
                with open(fn_xmlgz_asc, 'wb') as f:
                    f.write(blob.data)
                invalid_fns.append(fn_xmlgz_asc)

            # add to Jcat file too
            jcatitem.add_blob(blob)

        # write jcat file
        fn_xmlgz_jcat = fn_xmlgz + '.jcat'
        with open(fn_xmlgz_jcat, 'wb') as f:
            f.write(jcatfile.save())
        invalid_fns.append(fn_xmlgz_jcat)

    # update PULP
    for r in remotes:
        if r.name == 'stable':
            _metadata_update_pulp(download_dir)

    # do this all at once right at the end of all the I/O
    for fn in invalid_fns:
        print('Invalidating {}'.format(fn))
        ploader.file_modified(fn)

    # mark as no longer dirty
    for r in remotes:
        if not r.build_cnt:
            r.build_cnt = 0
        r.build_cnt += 1
        r.is_dirty = False
        db.session.commit()

    # drop caches in other sessions
    db.session.expire_all()

    # log what we did
    for r in remotes:
        _event_log('Signed metadata {} build {}'.format(r.name, r.build_cnt))

    # only keep the last 6 metadata builds (24h / stable refresh every 4h)
    for r in remotes:
        if not r.filename:
            continue
        suffix = r.filename.split('-')[2]
        fns = glob.glob(os.path.join(download_dir, 'firmware-*-{}'.format(suffix)))
        for fn in sorted(fns):
            build_cnt = int(fn.split('-')[1])
            if build_cnt + 6 > r.build_cnt:
                continue
            os.remove(fn)
            _event_log('Deleted metadata {} build {}'.format(r.name, build_cnt))

def _show_diff(blob_old, blob_new):
    fromlines = blob_old.decode().replace('\r', '').split('\n')
    tolines = blob_new.decode().split('\n')
    diff = difflib.unified_diff(fromlines, tolines)
    print('\n'.join(list(diff)[3:]))

def _sign_fw(fw):

    # load the .cab file
    download_dir = app.config['DOWNLOAD_DIR']
    fn = os.path.join(download_dir, fw.filename)
    try:
        with open(fn, 'rb') as f:
            cabarchive = CabArchive(f.read())
    except IOError as e:
        raise NotImplementedError('cannot read %s: %s' % (fn, str(e)))

    # create Jcat file
    jcatfile = JcatFile()

    # sign each component in the archive
    print('Signing: %s' % fn)
    for md in fw.mds:
        try:

            # create Jcat item with SHA1 and SHA256 checksum blob
            cabfile = cabarchive[md.filename_contents]
            jcatitem = jcatfile.get_item(md.filename_contents)
            jcatitem.add_blob(JcatBlobSha1(cabfile.buf))
            jcatitem.add_blob(JcatBlobSha256(cabfile.buf))

            # sign using plugins
            for blob in ploader.archive_sign(cabfile.buf):

                # add GPG only to archive for backwards compat with older fwupd
                if blob.kind == JcatBlobKind.GPG:
                    fn_blob = md.filename_contents + '.' + blob.filename_ext
                    cabarchive[fn_blob] = CabFile(blob.data)

                # add to Jcat file too
                jcatitem.add_blob(blob)

        except KeyError as _:
            raise NotImplementedError('no {} firmware found'.format(md.filename_contents))

    # rewrite the metainfo.xml file to reflect latest changes and sign it
    for md in fw.mds:

        # write new metainfo.xml file
        component = _generate_metadata_mds([md], metainfo=True)
        blob_xml = b'<?xml version="1.0" encoding="UTF-8"?>\n' + \
                   ET.tostring(component,
                               encoding='UTF-8',
                               xml_declaration=False,
                               pretty_print=True)
        _show_diff(cabarchive[md.filename_xml].buf, blob_xml)
        cabarchive[md.filename_xml].buf = blob_xml

        # sign it
        jcatitem = jcatfile.get_item(md.filename_xml)
        jcatitem.add_blob(JcatBlobSha1(blob_xml))
        jcatitem.add_blob(JcatBlobSha256(blob_xml))
        for blob in ploader.archive_sign(blob_xml):
            jcatitem.add_blob(blob)

    # write jcat file
    if jcatfile.items:
        cabarchive['firmware.jcat'] = CabFile(jcatfile.save())

    # overwrite old file
    cab_data = cabarchive.save()
    with open(fn, 'wb') as f:
        f.write(cab_data)

    # inform the plugin loader
    ploader.file_modified(fn)

    # update the download size
    for md in fw.mds:
        md.release_download_size = len(cab_data)

    # update the database
    fw.checksum_signed_sha1 = hashlib.sha1(cab_data).hexdigest()
    fw.checksum_signed_sha256 = hashlib.sha256(cab_data).hexdigest()
    fw.signed_timestamp = datetime.datetime.utcnow()
    db.session.commit()

def _repair_ts():

    # fix any timestamps that are incorrect
    for md in db.session.query(Component).filter(Component.release_timestamp < 1980):
        fn = _get_absolute_path(md.fw)
        if not os.path.exists(fn):
            continue
        print(fn, md.release_timestamp)
        try:
            ufile = UploadedFile(is_strict=False)
            for cat in db.session.query(Category):
                ufile.category_map[cat.value] = cat.category_id
            for pro in db.session.query(Protocol):
                ufile.protocol_map[pro.value] = pro.protocol_id
            with open(fn, 'rb') as f:
                ufile.parse(os.path.basename(fn), f.read())
        except MetadataInvalid as e:
            print('failed to parse file: {}'.format(str(e)))
            continue
        for md_local in ufile.fw.mds:
            if md_local.appstream_id == md.appstream_id:
                print('repairing timestamp from {} to {}'.format(md.release_timestamp,
                                                                 md_local.release_timestamp))
                md.release_timestamp = md_local.release_timestamp
                md.fw.mark_dirty()

    # all done
    db.session.commit()

def _fsck():
    for fw in db.session.query(Firmware):
        fn = _get_absolute_path(fw)
        if not os.path.isfile(fn):
            print('firmware {} is missing, expected {}'.format(fw.firmware_id, fn))

def _repair_csum():

    # fix all the checksums and file sizes
    for firmware_id in db.session.query(Firmware.firmware_id)\
                                 .order_by(Firmware.firmware_id.asc()):
        fw = db.session.query(Firmware)\
                       .filter(Firmware.firmware_id == firmware_id)\
                       .one()
        try:
            print('checking {}'.format(fw.filename_absolute))
            with open(fw.filename_absolute, 'rb') as f:
                checksum_signed_sha1 = hashlib.sha1(f.read()).hexdigest()
                if checksum_signed_sha1 != fw.checksum_signed_sha1:
                    print('repairing checksum from {} to {}'.format(fw.checksum_signed_sha1,
                                                                    checksum_signed_sha1))
                    fw.checksum_signed_sha1 = checksum_signed_sha1
                    fw.mark_dirty()
                checksum_signed_sha256 = hashlib.sha256(f.read()).hexdigest()
                if checksum_signed_sha256 != fw.checksum_signed_sha256:
                    print('repairing checksum from {} to {}'.format(fw.checksum_signed_sha256,
                                                                    checksum_signed_sha256))
                    fw.checksum_signed_sha256 = checksum_signed_sha256
                    fw.mark_dirty()
            for md in fw.mds:
                sz = os.path.getsize(fw.filename_absolute)
                if sz != md.release_download_size:
                    print('repairing size from {} to {}'.format(md.release_download_size, sz))
                    md.release_download_size = sz
                    md.fw.mark_dirty()
        except FileNotFoundError as _:
            pass

    # all done
    db.session.commit()

def _regenerate_and_sign_firmware():

    # find all unsigned firmware
    fws = db.session.query(Firmware).\
                        filter(Firmware.signed_timestamp == None).all()
    if not fws:
        return

    # sign each firmware in each file
    for fw in fws:
        if fw.is_deleted:
            continue
        print('Signing firmware %u...' % fw.firmware_id)
        _sign_fw(fw)
        _event_log('Signed firmware %s' % fw.firmware_id)

    # drop caches in other sessions
    db.session.expire_all()

def _ensure_tests():

    # ensure the test has been added for the firmware type
    for fw in db.session.query(Firmware).order_by(Firmware.timestamp):
        if not fw.is_deleted:
            ploader.ensure_test_for_fw(fw)
            db.session.commit()

def _delete_embargo_obsoleted_fw():

    # all embargoed firmware
    emails = defaultdict(list)
    for fw in db.session.query(Firmware)\
                        .join(Remote)\
                        .filter(Remote.name.startswith('embargo'))\
                        .order_by(Firmware.timestamp.asc()):

        # less than 6 months old
        if fw.target_duration < datetime.timedelta(days=30*6):
            continue

        # check that all the components are available with new versions
        all_newer = True
        print(fw.target_duration, fw.remote.name, fw.version_display)
        for md in fw.mds:
            md_newest = None
            for md_new in db.session.query(Component)\
                                    .join(Firmware)\
                                    .join(Remote)\
                                    .filter(Remote.is_public)\
                                    .filter(Component.appstream_id == md.appstream_id)\
                                    .order_by(Firmware.timestamp.asc()):
                if md_new > md or (md_newest and md_new > md_newest):
                    md_newest = md_new
                    break
            if not md_newest:
                all_newer = False
                print('no newer version of {} {}'.format(md.appstream_id,
                                                         md.version_display))
                break
            print('{} {} [{}] is newer than {} [{}]'.format(md.appstream_id,
                                                            md_newest.version_display,
                                                            md_newest.fw.remote.name,
                                                            md.version_display,
                                                            md.fw.remote.name))
        if not all_newer:
            continue

        # delete, but not purge for another 6 months...
        _firmware_delete(fw)

        # dedupe emails by user
        emails[fw.user].append(fw)

    # send email to the user that uploaded them, unconditionally
    for user in emails:
        send_email("[LVFS] Firmware has been obsoleted",
                   user.email_address,
                   render_template('email-firmware-obsolete.txt',
                                   user=user, fws=emails[user]))

    # all done
    db.session.commit()

def _purge_old_deleted_firmware():

    # find all unsigned firmware
    for fw in db.session.query(Firmware)\
                        .join(Remote).filter(Remote.name == 'deleted')\
                        .order_by(Firmware.timestamp.asc()):
        if fw.target_duration > datetime.timedelta(days=30*6):
            print('Deleting %s as age %s' % (fw.filename, fw.target_duration))
            path = os.path.join(app.config['RESTORE_DIR'], fw.filename)
            if os.path.exists(path):
                os.remove(path)
            for md in fw.mds:
                for shard in md.shards:
                    path = _get_shard_path(shard)
                    if os.path.exists(path):
                        os.remove(path)
            db.session.delete(fw)
            db.session.commit()

def _test_priority_sort_func(test):
    plugin = ploader.get_by_id(test.plugin_id)
    if not plugin:
        return 0
    return plugin.priority

def _yara_query_shard(query, md, shard):
    if not shard.blob:
        return
    matches = query.rules.match(data=shard.blob)
    for match in matches:
        msg = match.rule
        for string in match.strings:
            if len(string) == 3:
                try:
                    msg += ': found {}'.format(string[2].decode())
                except UnicodeDecodeError as _:
                    pass
        query.results.append(YaraQueryResult(md=md, shard=shard, result=msg))

    # unallocate the cached blob as it's no longer needed
    shard.blob = None

def _yara_query_component(query, md):
    if not md.blob:
        return
    matches = query.rules.match(data=md.blob)
    for match in matches:
        msg = match.rule
        for string in match.strings:
            if len(string) == 3:
                try:
                    msg += ': found {}'.format(string[2].decode())
                except UnicodeDecodeError as _:
                    pass
        query.results.append(YaraQueryResult(md=md, result=msg))

    # unallocate the cached blob as it's no longer needed
    md.blob = None

def _yara_query_all():

    # get all pending queries
    pending = db.session.query(YaraQuery).\
                    filter(YaraQuery.started_ts == None).\
                    filter(YaraQuery.error == None)
    if not pending:
        return

    # get list of component IDs (as integers)
    component_ids = [x[0] for x in db.session.query(Component.component_id)\
                                             .join(Firmware)\
                                             .join(Remote)\
                                             .filter(Remote.name == 'stable').all()]

    for query in pending:
        print('processing query {}: {}...'.format(query.yara_query_id, query.title))
        try:
            query.rules = yara.compile(source=query.value)
        except yara.SyntaxError as e:
            query.error = 'Failed to compile rules: {}'.format(str(e))
            db.session.commit()
            continue
        query.started_ts = datetime.datetime.utcnow()
        db.session.commit()
        for component_id in component_ids:
            md = db.session.query(Component)\
                           .filter(Component.component_id == component_id)\
                           .one()
            for shard in md.shards:
                _yara_query_shard(query, md, shard)
            _yara_query_component(query, md)
            query.total += len(md.shards)
        query.found = len(query.results)
        query.ended_ts = datetime.datetime.utcnow()
        db.session.commit()

def _check_firmware():

    # make a list of the first few tests that need running
    tests = db.session.query(Test)\
                      .filter(Test.started_ts == None)\
                      .order_by(Test.scheduled_ts)\
                      .limit(50).all()

    # mark all the tests as started
    for test in tests:
        print('Marking test {} started for firmware {}...'.format(test.plugin_id, test.fw.firmware_id))
        test.started_ts = datetime.datetime.utcnow()
    db.session.commit()

    # process each test
    for test in sorted(tests, key=_test_priority_sort_func):
        plugin = ploader.get_by_id(test.plugin_id)
        if not plugin:
            _event_log('No plugin %s' % test.plugin_id)
            test.ended_ts = datetime.datetime.utcnow()
            continue
        try:
            print('Running test {} for firmware {}'.format(test.plugin_id, test.fw.firmware_id))
            if hasattr(plugin, 'run_test_on_fw'):
                if hasattr(plugin, 'require_test_for_fw'):
                    if not plugin.require_test_for_fw(test.fw):
                        continue
                plugin.run_test_on_fw(test, test.fw)
            if hasattr(plugin, 'run_test_on_md'):
                for md in test.fw.mds:
                    if hasattr(plugin, 'require_test_for_md'):
                        if not plugin.require_test_for_md(md):
                            continue
                    plugin.run_test_on_md(test, md)
            test.ended_ts = datetime.datetime.utcnow()
            # don't leave a failed task running
            db.session.commit()
        except Exception as e: # pylint: disable=broad-except
            test.ended_ts = datetime.datetime.utcnow()
            test.add_fail('An exception occurred', str(e))

    # all done
    db.session.commit()


def _generate_stats_for_vendor(v, datestr):

    # is datestr older than firmware
    if not v.ctime:
        return
    if datestr < _get_datestr_from_datetime(v.ctime - datetime.timedelta(days=1)):
        return

    # get all the firmware for a specific vendor
    fw_ids = [fw.firmware_id for fw in v.fws]
    if not fw_ids:
        return

    # count how many times any of the firmware files were downloaded
    cnt = _execute_count_star(db.session.query(Client).\
                    filter(Client.firmware_id.in_(fw_ids)).\
                    filter(Client.datestr == datestr))
    analytic = AnalyticVendor(vendor_id=v.vendor_id, datestr=datestr, cnt=cnt)
    print('adding %s:%s = %i' % (datestr, v.group_id, cnt))
    db.session.add(analytic)

def _generate_stats_for_firmware(fw, datestr):

    # is datestr older than firmware
    if datestr < _get_datestr_from_datetime(fw.timestamp):
        return

    # count how many times any of the firmware files were downloaded
    cnt = _execute_count_star(db.session.query(Client).\
                    filter(Client.firmware_id == fw.firmware_id).\
                    filter(Client.datestr == datestr))
    analytic = AnalyticFirmware(firmware_id=fw.firmware_id, datestr=datestr, cnt=cnt)
    db.session.add(analytic)

def _demote_back_to_testing(fw):

    # from the server admin
    user = db.session.query(User).filter(User.username == 'anon@fwupd.org').first()
    if not user:
        return

    # send email to uploading user
    if fw.user.get_action('notify-demote-failures'):
        send_email("[LVFS] Firmware has been demoted",
                   fw.user.email_address,
                   render_template('email-firmware-demote.txt',
                                   user=fw.user, fw=fw))

    fw.mark_dirty()
    remote = db.session.query(Remote).filter(Remote.name == 'testing').first()
    remote.is_dirty = True
    fw.remote_id = remote.remote_id
    fw.events.append(FirmwareEvent(remote_id=fw.remote_id, user_id=user.user_id))
    db.session.commit()
    _event_log('Demoted firmware {} as reported success {}%'.format(fw.firmware_id, fw.success))

def _generate_stats_firmware_reports(fw):

    # count how many times any of the firmware files were downloaded
    reports_success = 0
    reports_failure = 0
    reports_issue = 0
    for r in db.session.query(Report).\
                    filter(Report.firmware_id == fw.firmware_id,
                           Report.timestamp > datetime.date.today() - datetime.timedelta(weeks=26)):
        if r.state == 2:
            reports_success += 1
        if r.state == 3:
            if r.issue_id:
                reports_issue += 1
            else:
                reports_failure += 1

    # update
    fw.report_success_cnt = reports_success
    fw.report_failure_cnt = reports_failure
    fw.report_issue_cnt = reports_issue

    # check the limits and demote back to embargo if required
    if fw.remote.name == 'stable' and fw.is_failure:
        _demote_back_to_testing(fw)

def _get_app_from_ua(ua):
    # always exists
    return ua.split(' ')[0]

def _get_fwupd_from_ua(ua):
    for part in ua.split(' '):
        if part.startswith('fwupd/'):
            return part[6:]
    return 'Unknown'

def _get_lang_distro_from_ua(ua):
    start = ua.find('(')
    end = ua.rfind(')')
    if start == -1 or end == -1:
        return None
    parts = ua[start+1:end].split('; ')
    if len(parts) != 3:
        return None
    return (parts[1], parts[2])

def _generate_stats_shard_info(info):

    cnt = db.session.query(ComponentShard.component_shard_id)\
                    .filter(ComponentShard.guid == info.guid)\
                    .count()
    if info.cnt != cnt:
        print('fixing ComponentShardInfo %i: %i -> %i' % (info.component_shard_info_id, info.cnt, cnt))
        info.cnt = cnt

def _generate_stats(kinds=None):
    if not kinds:
        kinds = ['FirmwareReport', 'ShardCount', 'ShardInfo', 'Metrics']

    # Set ComponentShardInfo in ComponentShard if GUID matches
    if 'Metrics' in kinds:
        print('stats::Metrics')
        values = {}
        values['ClientCnt'] = _execute_count_star(\
                                    db.session.query(Client))
        values['FirmwareCnt'] = _execute_count_star(\
                                    db.session.query(Firmware))
        values['FirmwareStableCnt'] = _execute_count_star(\
                                    db.session.query(Firmware)\
                                              .join(Remote)\
                                              .filter(Remote.name == 'stable'))
        values['FirmwareTestingCnt'] = _execute_count_star(\
                                    db.session.query(Firmware)\
                                              .join(Remote)\
                                              .filter(Remote.name == 'testing'))
        values['FirmwarePrivateCnt'] = _execute_count_star(\
                                    db.session.query(Firmware)\
                                              .join(Remote)\
                                              .filter(Remote.is_public == False))
        values['TestCnt'] = _execute_count_star(\
                                    db.session.query(Test))
        values['ReportCnt'] = _execute_count_star(\
                                    db.session.query(Report))
        values['ProtocolCnt'] = _execute_count_star(\
                                    db.session.query(Protocol))
        values['ComponentShardInfoCnt'] = _execute_count_star(\
                                    db.session.query(ComponentShardInfo))
        values['ComponentShardCnt'] = _execute_count_star(\
                                    db.session.query(ComponentShard))
        values['ComponentCnt'] = _execute_count_star(\
                                    db.session.query(Component))
        values['VendorCnt'] = _execute_count_star(\
                                    db.session.query(Vendor)\
                                              .filter(Vendor.visible)\
                                              .filter(Vendor.username_glob != None))
        values['UserCnt'] = _execute_count_star(\
                                    db.session.query(User)\
                                             .filter(User.auth_type != 'disabled'))

        #  save to database
        for key in values:
            metric = db.session.query(Metric).filter(Metric.key == key).first()
            if not metric:
                metric = Metric(key=key)
                db.session.add(metric)
            metric.value = values[key]
            print('{}={}'.format(metric.key, metric.value))
        db.session.commit()

    if 'ShardInfo' in kinds:
        print('stats::ShardInfo')
        infos = {}
        for info in db.session.query(ComponentShardInfo):
            infos[info.guid] = info
        for component_shard_id, in db.session.query(ComponentShard.component_shard_id).\
                            filter(ComponentShard.component_shard_info_id == None):
            shard = db.session.query(ComponentShard).\
                            filter(ComponentShard.component_shard_id == component_shard_id).one()
            shard.info = infos.get(shard.guid)
            if shard.info:
                print('fixing shard {} with {}'.format(component_shard_id, shard.guid))
            else:
                print('creating ComponentShardInfo for {}'.format(shard.guid))
                shard.info = ComponentShardInfo(guid=shard.guid)
                infos[shard.guid] = shard.info
            db.session.commit()

    # update ComponentShardInfo.cnt
    if 'ShardCount' in kinds:
        print('stats::ShardCount')
        for info_id, in db.session.query(ComponentShardInfo.component_shard_info_id)\
                                 .order_by(ComponentShardInfo.component_shard_info_id.asc()):
            info = db.session.query(ComponentShardInfo)\
                             .filter(ComponentShardInfo.component_shard_info_id == info_id)\
                             .one()
            _generate_stats_shard_info(info)
        db.session.commit()

    # update FirmwareReport counts
    if 'FirmwareReport' in kinds:
        print('stats::FirmwareReport')
        for fw in db.session.query(Firmware)\
                            .join(Remote).filter(Remote.name != 'deleted'):
            _generate_stats_firmware_reports(fw)
        db.session.commit()

    print('generated %s' % ','.join(kinds))

def _generate_stats_for_datestr(datestr, kinds=None):

    if not kinds:
        kinds = ['Analytic',
                 'AnalyticVendor',
                 'AnalyticFirmware',
                 'Useragent']

    # update AnalyticVendor
    if 'AnalyticVendor' in kinds:
        for analytic in db.session.query(AnalyticVendor).filter(AnalyticVendor.datestr == datestr):
            db.session.delete(analytic)
        db.session.commit()
        for v in db.session.query(Vendor):
            _generate_stats_for_vendor(v, datestr)
        db.session.commit()

    # update AnalyticFirmware
    if 'AnalyticFirmware' in kinds:
        for analytic in db.session.query(AnalyticFirmware).filter(AnalyticFirmware.datestr == datestr):
            db.session.delete(analytic)
        db.session.commit()
        for fw in db.session.query(Firmware)\
                            .join(Remote).filter(Remote.name != 'deleted'):
            _generate_stats_for_firmware(fw, datestr)
        db.session.commit()

    # update Useragent
    if 'Useragent' in kinds:
        for agnt in db.session.query(Useragent).filter(Useragent.datestr == datestr):
            db.session.delete(agnt)
        db.session.commit()
        ua_apps = {}
        ua_fwupds = {}
        ua_distros = {}
        ua_langs = {}
        clients = db.session.query(Client.user_agent).\
                        filter(Client.datestr == datestr).all()
        for res in clients:
            ua = res[0]
            if not ua:
                continue

            # downloader app
            ua_app = _get_app_from_ua(ua)
            if ua_app not in ua_apps:
                ua_apps[ua_app] = 1
            else:
                ua_apps[ua_app] += 1

            # fwupd version
            ua_fwupd = _get_fwupd_from_ua(ua)
            if ua_fwupd not in ua_fwupds:
                ua_fwupds[ua_fwupd] = 1
            else:
                ua_fwupds[ua_fwupd] += 1

            # language and distro
            ua_lang_distro = _get_lang_distro_from_ua(ua)
            if ua_lang_distro:
                ua_lang = ua_lang_distro[0]
                ua_distro = ua_lang_distro[1]
                if ua_lang not in ua_langs:
                    ua_langs[ua_lang] = 1
                else:
                    ua_langs[ua_lang] += 1
                if ua_distro not in ua_distros:
                    ua_distros[ua_distro] = 1
                else:
                    ua_distros[ua_distro] += 1
        for ua in ua_apps:
            db.session.add(Useragent(kind=int(UseragentKind.APP), value=ua, datestr=datestr, cnt=ua_apps[ua]))
        for ua in ua_fwupds:
            db.session.add(Useragent(kind=int(UseragentKind.FWUPD), value=ua, datestr=datestr, cnt=ua_fwupds[ua]))
        for ua in ua_langs:
            db.session.add(Useragent(kind=int(UseragentKind.LANG), value=ua, datestr=datestr, cnt=ua_langs[ua]))
        for ua in ua_distros:
            db.session.add(Useragent(kind=int(UseragentKind.DISTRO), value=ua, datestr=datestr, cnt=ua_distros[ua]))
        db.session.commit()

    # update Analytic
    if 'Analytic' in kinds:
        analytic = db.session.query(Analytic).filter(Analytic.datestr == datestr).first()
        if analytic:
            db.session.delete(analytic)
            db.session.commit()
        db.session.add(Analytic(datestr=datestr, cnt=len(clients)))
        db.session.commit()

    # for the log
    print('generated for %s: %s' % (datestr, ','.join(kinds)))

def _user_disable_notify():

    # find all users that have not logged in for over one year, and have never
    # been warned
    now = datetime.datetime.utcnow()
    for user in db.session.query(User)\
                          .filter(User.auth_type != 'disabled')\
                          .filter(User.atime < now - datetime.timedelta(days=365))\
                          .filter(User.unused_notify_ts == None):
        # send email
        send_email("[LVFS] User account unused: ACTION REQUIRED",
                   user.email_address,
                   render_template('email-unused.txt',
                                   user=user))
        user.unused_notify_ts = now
        db.session.commit()

def _user_disable_actual():

    # find all users that have an atime greater than 1 year and unused_notify_ts > 6 weeks */
    now = datetime.datetime.utcnow()
    for user in db.session.query(User)\
                          .filter(User.auth_type != 'disabled')\
                          .filter(User.atime < now - datetime.timedelta(days=365))\
                          .filter(User.unused_notify_ts < now - datetime.timedelta(days=42)):
        _event_log('Disabling user {} {} ({}) as unused'.format(user.user_id,
                                                                user.username,
                                                                user.display_name))
        user.auth_type = 'disabled'
        user.username = 'disabled_user{}@fwupd.org'.format(user.user_id)
        user.display_name = 'Disabled User {}'.format(user.user_id)
        db.session.commit()

def _main_with_app_context():
    if 'repair-ts' in sys.argv:
        _repair_ts()
    if 'repair-csum' in sys.argv:
        _repair_csum()
    if 'fsck' in sys.argv:
        _fsck()
    if 'ensure' in sys.argv:
        _ensure_tests()
    if 'firmware' in sys.argv:
        _regenerate_and_sign_firmware()
    if 'metadata' in sys.argv:
        _regenerate_and_sign_metadata()
    if 'metadata-embargo' in sys.argv:
        _regenerate_and_sign_metadata(only_embargo=True)
    if 'purgedelete' in sys.argv:
        _delete_embargo_obsoleted_fw()
        _purge_old_deleted_firmware()
    if 'fwchecks' in sys.argv:
        _check_firmware()
        _yara_query_all()
        _user_disable_notify()
        _user_disable_actual()
    if 'stats' in sys.argv:
        val = _get_datestr_from_datetime(datetime.date.today() - datetime.timedelta(days=1))
        _generate_stats_for_datestr(val)
        _generate_stats()
    if 'statsmigrate' in sys.argv:
        for days in range(1, 720):
            val = _get_datestr_from_datetime(datetime.date.today() - datetime.timedelta(days=days))
            _generate_stats_for_datestr(val)

if __name__ == '__main__':

    if len(sys.argv) < 2:
        print('Usage: %s [metadata] [firmware]' % sys.argv[0])
        sys.exit(1)
    try:
        with app.test_request_context():
            app.config['SERVER_NAME'] = app.config['HOST_NAME']
            g.user = db.session.query(User).filter(User.username == 'anon@fwupd.org').first()
            _main_with_app_context()
    except NotImplementedError as e:
        print(str(e))
        sys.exit(1)

    # success
    sys.exit(0)
