/*
 * Copyright (C) 2019 Richard Hughes <richard@hughsie.com>
 *
 * SPDX-License-Identifier: GPL-2.0+
 */
rule IbvExampleDmi
{
    meta:
        description = "IBV example DMI being used"
        waivable = true

    strings:
        $str1 = "To Be Defined By O.E.M" nocase wide ascii

    condition:
       $str1
}
