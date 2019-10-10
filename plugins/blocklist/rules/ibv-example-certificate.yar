/*
 * Copyright (C) 2019 Richard Hughes <richard@hughsie.com>
 *
 * SPDX-License-Identifier: GPL-2.0+
 */
rule IbvExampleCertificate
{
    meta:
        description = "IBV example certificate being used"
        waivable = false

    strings:
        $str1 = "DO NOT TRUST" nocase wide ascii
        $str2 = "DO NOT SHIP" nocase wide ascii

    condition:
       $str1 or $str2
}
