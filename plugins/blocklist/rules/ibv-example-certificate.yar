rule IbvExampleCertificate
{
    meta:
        author = "Richard Hughes <richard@hughsie.com>"
        license = "GPL-2.0+"
        description = "IBV example certificate being used"
        fail = true

    strings:
        $str1 = "DO NOT TRUST" nocase wide ascii
        $str2 = "DO NOT SHIP" nocase wide ascii

    condition:
       any of them
}
