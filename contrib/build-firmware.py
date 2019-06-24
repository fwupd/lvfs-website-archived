#!/usr/bin/python
# Copyright (C) 2015-2018 Richard Hughes <richard@hughsie.com>
#
# SPDX-License-Identifier: GPL-2.0+

import sys
import uuid
import struct

def _generate_fvme(buf, f):

    INTELME_PART_HEADER = '<16s4sIBBBBHHIIHHHH'
    INTELME_PART_ENTRY = '<4sIIIIIII'

    # header
    vect = b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'
    hdr = struct.pack(INTELME_PART_HEADER,
                      vect,     # vector
                      b'$FPT',  # Tag
                      1,        # NumPartitions
                      0x20,     # HeaderVersion
                      0x0,      # EntryVersion
                      struct.calcsize(INTELME_PART_HEADER), # HeaderLength
                      0x0,      # HeaderChecksum
                      0x0,      # FlashCycleLife
                      0x0,      # FlashCycleLimit
                      0x0,      # UMASize
                      0x0,      # Flags
                      0x0,      # FitMajor
                      0x0,      # FitMinor
                      0x0,      # FitHotfix
                      0x1)      # FitBuild
    f.write(hdr)

    # entry
    ent = struct.pack(INTELME_PART_ENTRY,
                      b'$MN2',  # sig
                      0x0,      # owner
                      0x0,      # offset
                      len(buf), # len
                      0x0,      # start_tokens
                      0x0,      # max_tokens
                      0x0,      # scratch_sectors
                      0x0)      # flags
    f.write(ent)
    f.write(buf)

def _generate_cap(buf, f):

    UEFI_CAPSULE_HEADER = '<16sIII'
    CAPSULE_FLAGS_PERSIST_ACROSS_RESET = 0x00010000
    CAPSULE_FLAGS_INITIATE_RESET = 0x00040000

    guid = uuid.UUID('{cc4cbfa9-bf9d-540b-b92b-172ce31013c1}').bytes_le
    hdr = struct.pack(UEFI_CAPSULE_HEADER,
                      guid,
                      struct.calcsize(UEFI_CAPSULE_HEADER),
                      CAPSULE_FLAGS_PERSIST_ACROSS_RESET | CAPSULE_FLAGS_INITIATE_RESET,
                      struct.calcsize(UEFI_CAPSULE_HEADER) + len(buf))
    f.write(hdr)
    f.write(buf)

def _generate_pfs(buf, f):

    # write a section header without any signature or metadata
    guid = uuid.UUID('{12345678-1234-5678-1234-567812345678}')
    version = struct.pack('<HHHH', 1, 2, 3, 4)
    sec = struct.pack('<16sI4s8sQIIII16s',
                      guid.bytes_le,# Guid1
                      0x1,          # HeaderVersion (always 1)
                      b'AAAA',      # VersionType
                      version,      # Version
                      0x0,          # Reserved
                      len(buf),    # DataSize
                      0x0,          # DataSignatureSize
                      0x0,          # MetadataSize
                      0x0,          # MetadataSignatureSize
                      guid.bytes_le)# Guid2

    # write header
    hdr = struct.pack('<8sII',
                      b'PFS.HDR.',  # Signature
                      0x1,          # HeaderVersion (always 1)
                      len(buf) + len(sec)) # DataSize
    f.write(hdr)

    # write footer
    ftr = struct.pack('<II8s',
                      len(buf) + len(sec), # DataSize
                      0x0,          # Checksum (disabled)
                      b'PFS.FTR.')  # Signature

    # write to disk
    f.write(sec)
    f.write(buf)
    f.write(ftr)

def _len24(val):
    return struct.pack('<BBB', val & 0xff, (val >> 8) & 0xff, (val >> 16) & 0xff)

def _generate_fvh(buf, f):

    EFI_FIRMWARE_VOLUME_HEADER = '<16s16sQ4sIHHHBB'
    EFI_FV_BLOCK_MAP_ENTRY = '<II'
    EFI_FFS_FILE_HEADER = '<16sHBB3sB'
    EFI_COMMON_SECTION_HEADER = '<3sB'

    # EFI_FIRMWARE_VOLUME_HEADER
    vect = b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'
    guid = b'\x78\xe5\x8c\x8c\x3d\x8a\x1c\x4f\x99\x35\x89\x61\x85\xc3\x2d\xd3'
    hdr = struct.pack(EFI_FIRMWARE_VOLUME_HEADER,
                      vect,         # Signature
                      guid,         # FileSystemGuid
                      struct.calcsize(EFI_FIRMWARE_VOLUME_HEADER) +
                      struct.calcsize(EFI_FV_BLOCK_MAP_ENTRY) +
                      struct.calcsize(EFI_FFS_FILE_HEADER) +
                      len(buf) +
                      struct.calcsize(EFI_COMMON_SECTION_HEADER) +
                      struct.calcsize(EFI_FV_BLOCK_MAP_ENTRY),  # FvLength
                      b'_FVH',      # Signature
                      0x0,          # Attributes
                      struct.calcsize(EFI_FIRMWARE_VOLUME_HEADER) +
                      struct.calcsize(EFI_FV_BLOCK_MAP_ENTRY) +
                      struct.calcsize(EFI_FV_BLOCK_MAP_ENTRY),  # HeaderLength
                      0x0,          # Checksum FIXME (header sums to zero)
                      0x0,          # ExtHeaderOffset
                      0x0,          # Reserved
                      0x02)         # Revision

    # no need to align, as header is already 8-byte aligned
    f.write(hdr)

    # EFI_FV_BLOCK_MAP_ENTRY
    ent = struct.pack(EFI_FV_BLOCK_MAP_ENTRY,
                      0x1, # just one block
                      struct.calcsize(EFI_FIRMWARE_VOLUME_HEADER) +
                      struct.calcsize(EFI_FV_BLOCK_MAP_ENTRY) +
                      struct.calcsize(EFI_FFS_FILE_HEADER) +
                      len(buf) +
                      struct.calcsize(EFI_COMMON_SECTION_HEADER) +
                      struct.calcsize(EFI_FV_BLOCK_MAP_ENTRY)) # same as FvLength
    f.write(ent)

    # EFI_FV_BLOCK_MAP_ENTRY
    eof = struct.pack(EFI_FV_BLOCK_MAP_ENTRY, 0x0, 0x0)
    f.write(eof)

    # EFI_FFS_FILE_HEADER
    guid = uuid.UUID('{12345678-1234-5678-1234-567812345678}').bytes_le
    fle = struct.pack(EFI_FFS_FILE_HEADER,
                      guid,         # Name
                      0x0,          # IntegrityCheck
                      0x07,         # Type (DRIVER)
                      0x0,          # Attributes
                      _len24(len(buf) +
                             struct.calcsize(EFI_COMMON_SECTION_HEADER) +
                             struct.calcsize(EFI_FFS_FILE_HEADER)), # Size
                      0x4)          # State (DATA_VALID)
    f.write(fle)

    # EFI_COMMON_SECTION_HEADER
    shd = struct.pack(EFI_COMMON_SECTION_HEADER,
                      _len24(len(buf) + \
                             struct.calcsize(EFI_COMMON_SECTION_HEADER)), # Size
                      0x10)         # Type (EFI_SECTION_PE32)
    f.write(shd)
    f.write(buf)

if __name__ == '__main__':

    if len(sys.argv) != 3:
        print('Usage: %s in.bin out.pfs' % sys.argv[0])
        sys.exit(1)
    with open(sys.argv[1], 'rb') as f_in:
        with open(sys.argv[2], 'wb') as f_out:
            _buf = f_in.read()
            if sys.argv[2].endswith('.pfs'):
                _generate_pfs(_buf, f_out)
            elif sys.argv[2].endswith('.fvh'):
                _generate_fvh(_buf, f_out)
            elif sys.argv[2].endswith('.cap'):
                _generate_cap(_buf, f_out)
            elif sys.argv[2].endswith('.fvme'):
                _generate_fvme(_buf, f_out)
