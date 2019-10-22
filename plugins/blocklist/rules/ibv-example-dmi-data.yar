rule IbvExampleDmi
{
    meta:
        author = "Richard Hughes <richard@hughsie.com>"
        license = "GPL-2.0+"
        description = "IBV example DMI being used"
        waivable = true

    strings:
        $str1 = "To Be Defined By O.E.M" nocase wide ascii

    condition:
       any of them
}
