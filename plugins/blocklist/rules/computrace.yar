rule ComputraceAgent
{
    meta:
        license = "GPL-2.0+"
        description = "Absolute Computrace Agent Executable"
        fail = false
        claim = "info-computrace"

    strings:
        $a = {D1 E0 F5 8B 4D 0C 83 D1 00 8B EC FF 33 83 C3 04}
        $mz = {4d 5a}
        $b1 = {72 70 63 6E 65 74 70 2E 65 78 65 00 72 70 63 6E 65 74 70 00}
        $b2 = {54 61 67 49 64 00}

    condition:
        ($mz at 0) and ($a or ($b1 and $b2))
}
