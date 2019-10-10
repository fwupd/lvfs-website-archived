/*
 * Copyright (C) 2019 Richard Hughes <richard@hughsie.com>
 *
 * SPDX-License-Identifier: GPL-2.0+
 */
rule DualEcBackdoorForNsa
{
    meta:
        description = "Contains the Dual EC backdoor for the NSA"
        waivable = false

    strings:
        $str1 = "c97445f45cdef9f0d3e05e1e585fc297235b82b5be8ff3efca67c59852018192" nocase wide ascii

    condition:
       $str1
}
