#!/usr/bin/python2
# -*- coding: utf-8 -*-
#
# Copyright (C) 2015 Richard Hughes <richard@hughsie.com>
#
# This library is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License as published by the Free Software Foundation; either
# version 2.1 of the License, or (at your option) any later version.
#
# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public
# License along with this library; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston,
# MA 02110-1301, USA

import os
import struct
import fnmatch
import zlib
import datetime

from file import CabFile
from errors import *

FMT_CFHEADER = '<4sxxxxIxxxxIxxxxBBHHHHH'
FMT_CFFOLDER = '<IHH'
FMT_CFFILE = '<IIHHHH'
FMT_CFDATA = '<IHH'

def _chunkify(arr, size):
    """ Split up a bytestream into chunks """
    arrs = []
    for i in range(0, len(arr), size):
        chunk = bytearray(arr[i:i+size])
        arrs.append(chunk)
    return arrs

def _checksum_compute(content, seed=0):
    """ Compute the MS cabinet checksum """
    csum = seed
    chunks = _chunkify(content, 4)
    for chunk in chunks:
        if len(chunk) == 4:
            ul = chunk[0]
            ul |= chunk[1] << 8
            ul |= chunk[2] << 16
            ul |= chunk[3] << 24
        else:
            # WTF: I can only assume this is a typo from the original
            # author of the cabinet file specification
            if len(chunk) == 3:
                ul = (chunk[0] << 16) | (chunk[1] << 8) | chunk[2]
            elif len(chunk) == 2:
                ul = (chunk[0] << 8) | chunk[1]
            elif len(chunk) == 1:
                ul = chunk[0]
        csum ^= ul
    return csum

class CabArchive(object):
    """An object representing a Microsoft Cab archive """

    def __init__(self):
        """ Set defaults """
        self.files = []
        self.set_id = 0
        self._buf_file = None
        self._folder_data = []
        self._is_multi_folder = False

    def add_file(self, cffile):
        """ Add file to archive """

        # remove old file if already present
        for tmp in self.files:
            if tmp.filename == cffile.filename:
                self.files.remove(tmp)
                break

        # add object
        self.files.append(cffile)

    def _parse_cffile(self, offset):
        """ Parse a CFFILE entry """
        fmt = '<I'      # uncompressed size
        fmt += 'I'      # uncompressed offset of this file in the folder
        fmt += 'H'      # index into the CFFOLDER area
        fmt += 'H'      # date
        fmt += 'H'      # time
        fmt += 'H'      # attribs
        try:
            vals = struct.unpack_from(fmt, self._buf_file, offset)
        except struct.error as e:
            raise CorruptionError(str(e))

        # debugging
        if os.getenv('PYTHON_CABARCHIVE_DEBUG'):
            print "CFFILE", vals

        # parse filename
        offset += struct.calcsize(fmt)
        filename = ''
        for i in range(0, 255):
            filename_c = self._buf_file[offset + i]
            if filename_c == b'\0':
                break
            filename += filename_c

        # add file
        f = CabFile(filename)
        f._date_decode(vals[3])
        f._time_decode(vals[4])
        f._attr_decode(vals[5])
        f.contents = self._folder_data[vals[2]][vals[1]:vals[1] + vals[0]]
        if len(f.contents) != vals[0]:
            raise CorruptionError("Corruption inside archive, %s is size %i but "
                                  "expected size %i" % (filename, len(f.contents), vals[0]))
        self.files.append(f)

        # return offset to next entry
        return 16 + len(filename) + 1

    def _parse_cffolder(self, idx, offset):
        """ Parse a CFFOLDER entry """
        fmt = '<I'      # offset to CFDATA
        fmt += 'H'      # number of CFDATA blocks
        fmt += 'H'      # compression type
        try:
            vals = struct.unpack_from(fmt, self._buf_file, offset)
        except struct.error as e:
            raise CorruptionError(str(e))

        # debugging
        if os.getenv('PYTHON_CABARCHIVE_DEBUG'):
            print "CFFOLDER", vals

        # no data blocks?
        if vals[1] == 0:
            raise CorruptionError('No CFDATA blocks')

        # no compression is supported
        if vals[2] == 0:
            is_zlib = False
        elif vals[2] == 1:
            is_zlib = True
        else:
            raise NotSupportedError('Compression type not supported')

        # not supported
        if is_zlib and self._is_multi_folder:
            raise NotSupportedError("Compression unsupported in multi-folder archive: "
                                    "set FolderSizeThreshold=0 in the .ddf file")

        # parse CDATA
        self._folder_data.append(bytearray())
        offset = vals[0]
        for i in range(vals[1]):
            offset += self._parse_cfdata(idx, offset, is_zlib)

    def _parse_cfdata(self, idx, offset, is_zlib):
        """ Parse a CFDATA entry """
        fmt = '<I'      # checksum
        fmt += 'H'      # compressed bytes
        fmt += 'H'      # uncompressed bytes
        try:
            vals = struct.unpack_from(fmt, self._buf_file, offset)
        except struct.error as e:
            raise CorruptionError(str(e))
        # debugging
        if os.getenv('PYTHON_CABARCHIVE_DEBUG'):
            print "CFDATA", vals
        if not is_zlib and vals[1] != vals[2]:
            raise CorruptionError('Mismatched data %i != %i' % (vals[1], vals[2]))
        hdr_sz = struct.calcsize(fmt)
        newbuf = self._buf_file[offset + hdr_sz:offset + hdr_sz + vals[1]]

        # decompress Zlib data after removing *another* header...
        if is_zlib:
            if newbuf[0] != 'C' or newbuf[1] != 'K':
                raise CorruptionError('Compression header invalid')
            decompress = zlib.decompressobj(-zlib.MAX_WBITS)
            try:
                buf = decompress.decompress(newbuf[2:])
                buf += decompress.flush()
            except zlib.error as e:
                raise CorruptionError('Failed to decompress: ' + str(e))
        else:
            buf = newbuf

        # check checksum
        if vals[0] != 0:
            checksum = _checksum_compute(newbuf)
            hdr = bytearray(struct.pack('<HH', len(newbuf), len(buf)))
            checksum = _checksum_compute(hdr, checksum)
            if checksum != vals[0]:
                raise CorruptionError("Got checksum %04x, expected %04x" % (vals[0], checksum))

        assert len(buf) == vals[2]
        self._folder_data[idx] += buf
        return vals[1] + hdr_sz

    def parse(self, buf):
        """ Parse .cab data """

        # slurp the whole buffer at once
        self._buf_file = buf

        # read the file header
        fmt = '<4s'     # signature
        fmt += 'xxxx'   # reserved1
        fmt += 'I'      # size
        fmt += 'xxxx'   # reserved2
        fmt += 'I'      # offset to CFFILE
        fmt += 'xxxx'   # reserved3
        fmt += 'BB'     # version minor, major
        fmt += 'H'      # no of CFFOLDERs
        fmt += 'H'      # no of CFFILEs
        fmt += 'H'      # flags
        fmt += 'H'      # setID
        fmt += 'H'      # cnt of cabs in set
#        fmt += 'H'      # reserved cab size
#        fmt += 'B'      # reserved folder size
#        fmt += 'B'      # reserved block size
#        fmt += 'B'      # per-cabinet reserved area
        try:
            vals = struct.unpack_from(fmt, self._buf_file, 0)
        except struct.error as e:
            raise CorruptionError(str(e))

        # debugging
        if os.getenv('PYTHON_CABARCHIVE_DEBUG'):
            print "CFHEADER", vals

        # check magic bytes
        if vals[0] != b'MSCF':
            raise NotSupportedError('Data is not application/vnd.ms-cab-compressed')

        # check size matches
        if vals[1] != len(self._buf_file):
            raise CorruptionError('Cab file internal size does not match data')

        # check version
        if vals[4] != 1  or vals[3] != 3:
            raise NotSupportedError('Version %i.%i not supported' % (vals[4], vals[3]))

        # chained cabs not supported
        if vals[9] != 0:
            raise NotSupportedError('Chained cab file not supported')

        # verify we actually have data
        nr_files = vals[6]
        if nr_files == 0:
            raise CorruptionError('The cab file is empty')

        # verify we got complete data
        off_cffile = vals[2]
        if off_cffile > len(self._buf_file):
            raise CorruptionError('Cab file corrupt')

        # chained cabs not supported
        if vals[7] != 0:
            raise CorruptionError('Expected header flags to be cleared')

        # read this so we can do round-trip
        self.set_id = vals[8]

        # we don't support compressed folders in multi-folder archives
        if vals[5] > 1:
            self._is_multi_folder = True

        # parse CFFOLDER
        offset = struct.calcsize(fmt)
        for i in range(vals[5]):
            self._parse_cffolder(i, offset)
            offset += struct.calcsize(FMT_CFFOLDER)

        # parse CFFILEs
        for i in range(0, nr_files):
            off_cffile += self._parse_cffile(off_cffile)

    def parse_file(self, filename):
        """ Parse a .cab file """
        self.parse(open(filename, 'rb').read())

    def find_file(self, glob):
        """ Gets a file from the archive using a glob """
        for cf in self.files:
            if fnmatch.fnmatch(cf.filename, glob):
                return cf
        return None

    def find_files(self, glob):
        """ Gets files from the archive using a glob """
        arr = []
        for cf in self.files:
            if fnmatch.fnmatch(cf.filename, glob):
                arr.append(cf)
        return arr

    def save(self, compressed=False):
        """ Returns cabinet file data """

        # create linear CFDATA block
        cfdata_linear = bytearray()
        for f in self.files:
            cfdata_linear += f.contents

        # _chunkify and compress with a fixed size
        chunks = _chunkify(cfdata_linear, 0x8000)
        if compressed:
            chunks_zlib = []
            for chunk in chunks:
                compress = zlib.compressobj(9, zlib.DEFLATED, -zlib.MAX_WBITS)
                chunk_zlib = bytearray('CK')
                chunk_zlib += compress.compress(str(chunk))
                chunk_zlib += compress.flush()
                chunks_zlib.append(chunk_zlib)
        else:
            chunks_zlib = chunks

        # create header
        archive_size = struct.calcsize(FMT_CFHEADER)
        archive_size += struct.calcsize(FMT_CFFOLDER)
        for f in self.files:
            archive_size += struct.calcsize(FMT_CFFILE) + len(f.filename) + 1
        for chunk in chunks_zlib:
            archive_size += struct.calcsize(FMT_CFDATA) + len(chunk)
        offset = struct.calcsize(FMT_CFHEADER)
        offset += struct.calcsize(FMT_CFFOLDER)
        data = struct.pack(FMT_CFHEADER,
                           'MSCF',                  # signature
                           archive_size,            # complete size
                           offset,                  # offset to CFFILE
                           3, 1,                    # ver minor major
                           1,                       # no of CFFOLDERs
                           len(self.files),         # no of CFFILEs
                           0,                       # flags
                           self.set_id,             # setID
                           0)                       # cnt of cabs in set

        # create folder
        for f in self.files:
            offset += struct.calcsize(FMT_CFFILE)
            offset += len(f.filename) + 1
        data += struct.pack(FMT_CFFOLDER,
                            offset,                 # offset to CFDATA
                            len(chunks),            # number of CFDATA blocks
                            compressed)             # compression type

        # create each CFFILE
        index_into = 0
        for f in self.files:
            data += struct.pack(FMT_CFFILE,
                                len(f.contents),    # uncompressed size
                                index_into,         # uncompressed offset
                                0,                  # index into CFFOLDER
                                f._date_encode(),   # date
                                f._time_encode(),   # time
                                f._attr_encode())   # attribs
            data += f.filename + b'\0'
            index_into += len(f.contents)

        # create each CFDATA
        for i in range(0, len(chunks)):
            chunk = chunks[i]
            chunk_zlib = chunks_zlib[i]

            # first do the 'checksum' on the data, then the partial
            # header. slightly crazy, but anyway
            checksum = _checksum_compute(chunk_zlib)
            hdr = bytearray(struct.pack('<HH', len(chunk_zlib), len(chunk)))
            checksum = _checksum_compute(hdr, checksum)
            data += struct.pack(FMT_CFDATA,
                                checksum,           # checksum
                                len(chunk_zlib),    # compressed bytes
                                len(chunk))         # uncompressed bytes
            data += chunk_zlib

        # return bytearray
        return data

    def save_file(self, filename, compressed=False):
        """ Saves a cabinet file to disk """
        data = self.save(compressed)
        open(filename, 'wb').write(data)

    def __repr__(self):
        """ Represent the object as a string """
        return "<CabArchive object %s>" % self.files
