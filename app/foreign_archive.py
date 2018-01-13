#!/usr/bin/python2
# -*- coding: utf-8 -*-
#
# Copyright (C) 2015-2018 Richard Hughes <richard@hughsie.com>
# Licensed under the GNU General Public License Version 2

import os
import shutil
import subprocess
import tempfile

import cabarchive

def _listdir_recurse(basedir):
    """ Return all files and folders """
    files = []
    for res in os.listdir(basedir):
        fn = os.path.join(basedir, res)
        if not os.path.isfile(fn):
            children = _listdir_recurse(fn)
            files.extend(children)
            continue
        files.append(fn)
    return files

def _build_cab(filename, buf, tmpdir=None):

    # write to temp file
    src = tempfile.NamedTemporaryFile(mode='wb',
                                      prefix='foreignarchive_',
                                      suffix=".cab",
                                      dir=tmpdir,
                                      delete=True)
    src.write(buf)
    src.flush()

    # decompress to a temp directory
    dest_fn = tempfile.mkdtemp(prefix='foreignarchive_', dir=tmpdir)

    # work out what binary to use
    split = filename.rsplit('.', 1)
    if len(split) < 2:
        raise cabarchive.NotSupportedError('Filename not valid')
    if split[1] == 'zip':
        argv = ['/usr/bin/bsdtar', '--directory', dest_fn, '-xvf', src.name]
    elif split[1] == 'cab':
        argv = ['/usr/bin/cabextract', '--quiet', '--directory', dest_fn, src.name]
    else:
        raise cabarchive.NotSupportedError('Filename had no supported extension')

    # extract
    ps = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if ps.wait() != 0:
        raise cabarchive.CorruptionError('Failed to extract: %s' % ps.stderr.read())

    # add all the fake CFFILE objects
    arc = cabarchive.CabArchive()
    for fn in _listdir_recurse(dest_fn):
        cff = cabarchive.CabFile(os.path.basename(fn.replace('\\', '/')))
        cff.contents = open(fn, 'rb').read()
        arc.add_file(cff)
    shutil.rmtree(dest_fn)
    src.close()
    return arc
