#!/usr/bin/python2
# -*- coding: utf-8 -*-
#
# Copyright (C) 2018 Richard Hughes <richard@hughsie.com>
# Licensed under the GNU General Public License Version 2

import os
import gnupg

from gi.repository import Gio
from gi.repository import GLib
from gi.repository import GCab

from app.pluginloader import PluginBase, PluginError, PluginSettingText
from app import db, ploader
from app.util import _archive_get_files_from_glob

class Affidavit(object):

    """ A quick'n'dirty signing server """
    def __init__(self, key_uid=None, homedir='/tmp'):
        """ Set defaults """

        # check exists
        if not os.path.exists(homedir):
            try:
                os.mkdir(homedir)
            except OSError as e:
                raise PluginError(e)

        # find correct key ID for the UID
        self._keyid = None
        gpg = gnupg.GPG(gnupghome=homedir, gpgbinary='gpg2')
        for privkey in gpg.list_keys(True):
            for uid in privkey['uids']:
                if uid.find(key_uid) != -1:
                    self._keyid = privkey['keyid']
        if not self._keyid:
            raise PluginError('No imported private key for %s' % key_uid)
        self._homedir = homedir

    def create(self, data):
        """ Create detached signature data """
        gpg = gnupg.GPG(gnupghome=self._homedir, gpgbinary='gpg2')
        return str(gpg.sign(str(data), detach=True, keyid=self._keyid))

    def create_detached(self, filename):
        """ Create a detached signature file """
        data = open(filename).read()
        with open(filename + '.asc', 'w') as f:
            f.write(self.create(data))
        return filename + '.asc'

    def verify(self, data):
        """ Verify that the data was signed by something we trust """
        gpg = gnupg.GPG(gnupghome=self._homedir, gpgbinary='gpg2')
        ver = gpg.verify(data)
        if not ver.valid:
            raise PluginError('Firmware was signed with an unknown private key')
        return True

class Plugin(PluginBase):
    def __init__(self):
        PluginBase.__init__(self)

    def name(self):
        return 'Sign GPG'

    def settings(self):
        s = []
        s.append(PluginSettingText('sign_gpg_keyring_dir', 'Keyring Directory'))
        s.append(PluginSettingText('sign_gpg_signing_uid', 'Signing UID'))
        return s

    def _create_affidavit(self):
        """ Create an affidavit that can be used to sign files """
        settings = db.settings.get_filtered('sign_gpg_')
        if not settings['signing_uid']:
            return None
        if not settings['keyring_dir']:
            return None
        return Affidavit(settings['signing_uid'], settings['keyring_dir'])

    def _metadata_modified(self, fn):

        # generate
        affidavit = self._create_affidavit()
        if not affidavit:
            return
        blob = open(fn, 'rb').read()
        blob_asc = affidavit.create(blob)
        fn_asc = fn + '.asc'
        with open(fn_asc, 'w') as f:
            f.write(blob_asc)

        # inform the plugin loader
        ploader.file_modified(fn_asc)

    def file_modified(self, fn):
        if fn.endswith('.xml.gz'):
            self._metadata_modified(fn)

    def archive_sign(self, arc, firmware_cff):

        # does the detached signature already exist?
        detached_fn = firmware_cff.get_name() + '.asc'
        if _archive_get_files_from_glob(arc, detached_fn):
            print "file %s is already GPG signed" % firmware_cff.get_name()
            return

        # create the detached signature
        affidavit = self._create_affidavit()
        if not affidavit:
            return
        contents = firmware_cff.get_bytes().get_data()
        contents_asc = affidavit.create(contents)
        asc_cff = GCab.File.new_with_bytes(detached_fn, GLib.Bytes.new(contents_asc))

        # add it to the archive
        folders = arc.get_folders()
        if not folders:
            print 'archive has no folders'
            return
        folders[0].add_file(asc_cff, False)
