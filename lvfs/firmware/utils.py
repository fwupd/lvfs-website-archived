#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2017-2018 Richard Hughes <richard@hughsie.com>
#
# SPDX-License-Identifier: GPL-2.0+
#
# pylint: disable=singleton-comparison

import os
import shutil
import difflib
import hashlib
import datetime

from collections import defaultdict

from lxml import etree as ET
from flask import render_template, g

from jcat import JcatFile, JcatBlobSha1, JcatBlobSha256, JcatBlobKind
from cabarchive import CabArchive, CabFile

from lvfs import app, db, celery, ploader
from lvfs.emails import send_email
from lvfs.models import Remote, Firmware, FirmwareEvent, Component
from lvfs.util import _event_log, _get_shard_path
from lvfs.metadata.utils import _generate_metadata_mds, _async_regenerate_remote
from lvfs.metadata.utils import _regenerate_and_sign_metadata_remote

def _firmware_delete(fw):

    # find private remote
    remote = db.session.query(Remote).filter(Remote.name == 'deleted').first()
    if not remote:
        _event_log('No deleted remote')
        return

    # move file so it's no longer downloadable
    path = os.path.join(app.config['DOWNLOAD_DIR'], fw.filename)
    if os.path.exists(path):
        path_new = os.path.join(app.config['RESTORE_DIR'], fw.filename)
        shutil.move(path, path_new)

    # generate next cron run
    fw.mark_dirty()

    # mark as invalid
    fw.remote_id = remote.remote_id
    fw.events.append(FirmwareEvent(remote_id=fw.remote_id, user_id=g.user.user_id))
    db.session.commit()

    # asynchronously sign
    _async_regenerate_remote.apply_async(args=(fw.remote.remote_id,), queue='metadata')

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
        print('{} {} {}'.format(fw.target_duration, fw.remote.name, fw.version_display))
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

        # delete, but not purge...
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
    for firmware_id, in db.session.query(Firmware.firmware_id)\
                                  .join(Remote).filter(Remote.name == 'deleted')\
                                  .order_by(Firmware.timestamp.asc()):
        fw = db.session.query(Firmware)\
                       .filter(Firmware.firmware_id == firmware_id)\
                       .one()
        if fw.target_duration > datetime.timedelta(days=30):
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

@celery.task(max_retries=3, default_retry_delay=360, task_time_limit=60)
def _async_autodelete():
    _delete_embargo_obsoleted_fw()
    _purge_old_deleted_firmware()

def _show_diff(blob_old, blob_new):
    fromlines = blob_old.decode().replace('\r', '').split('\n')
    tolines = blob_new.decode().split('\n')
    diff = difflib.unified_diff(fromlines, tolines)
    print('\n'.join(list(diff)[3:]))

@celery.task(max_retries=3, default_retry_delay=5, task_time_limit=60)
def _async_sign_fw(firmware_id):
    fw = db.session.query(Firmware)\
                   .filter(Firmware.firmware_id == firmware_id)\
                   .filter(Firmware.is_dirty)\
                   .first()
    if not fw:
        return
    _sign_fw(fw)

    # just do it now
    fw.remote.is_dirty = True
    if not fw.remote.is_public:
        _regenerate_and_sign_metadata_remote(fw.remote)

def _sign_fw(fw):

    # already being regenerated
    if fw.is_regenerating:
        return

    # load the .cab file
    download_dir = app.config['DOWNLOAD_DIR']
    fn = os.path.join(download_dir, fw.filename)
    try:
        with open(fn, 'rb') as f:
            cabarchive = CabArchive(f.read())
    except IOError as e:
        raise NotImplementedError('cannot read %s' % fn) from e

    # claim this
    fw.regenerate_ts = datetime.datetime.utcnow()
    db.session.commit()

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

        except KeyError as e:
            raise NotImplementedError('no {} firmware found'.format(md.filename_contents)) from e

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

    # release this
    fw.regenerate_ts = None
    db.session.commit()

    # log
    _event_log('Signed firmware %s' % fw.firmware_id)

def _sign_firmware_all():

    # find all unsigned firmware
    fws = db.session.query(Firmware)\
                    .filter(Firmware.signed_timestamp == None).all()
    if not fws:
        return

    # sign each firmware in each file
    for fw in fws:
        if fw.is_deleted:
            continue
        _sign_fw(fw)

    # drop caches in other sessions
    #db.session.expire_all()
