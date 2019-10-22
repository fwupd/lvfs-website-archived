rule DualEcBackdoorForNsa
{
    meta:
        author = "Richard Hughes <richard@hughsie.com>"
        license = "GPL-2.0+"
        description = "Contains the Dual EC backdoor for the NSA"
        waivable = false

    strings:
        $str1 = "c97445f45cdef9f0d3e05e1e585fc297235b82b5be8ff3efca67c59852018192" nocase wide ascii

    condition:
       any of them
}
