Claims
######

Firmware uploaded to the LVFS is scanned, and attributes about the update are added
automatically.

Some claims may be positive, for instance if hardware supports verification.
Negative claims are also added, for instance if verification checksums are missing.
Informational *neutral* claims are also added, which are not positive or negative,
but may be a consideration for the user, e.g. if Computrace is included.

UEFI Shell
==========

Including the Shell.efi in a firmware update can create additional supply chain
security risks.
From the UEFI shell it is very easy to downgrade processor microcode or to abuse
the existing update process.
It also makes attacking SMI handlers much easier, e.g. `ThinkPwn <https://github.com/Cr4sh/ThinkPwn>`_.

The EFI shell allows direct RW access to memory using ``mm`` command, which by
itself defeats SecureBoot and everything else that's security is based on memory
not being being attacker-controlled.

Old Microcode
=============

Processor microcode can be thought of runtime firmware for the CPU processor itself.
It maps "high level" x86 instructions to hardware micro-opcodes that are specific
to the processor.
Microcode is supplied as an encrypted blob by CPU vendors like Intel and AMD
and cannot be modified in any way by the end user.
Only microcode signed by the processor vendor can be loaded onto the CPU.

In some cases, the processor vendor will issue a new microcode to address an issue,
which may be security sensitive.
This has been done many times in the past, e.g. to fix or mitigate the Spectre,
Meltdown and Foreshadow security issues.
In some cases microcode updates are even done to increase performance for a
specific workload.

If a firmware is tagged as *_containing old microcode* it doesn't always mean
that there is an unpatched security issue.
Some microcode is vendor-specific, so for instance Lenovo might create an update
on the LVFS that updates the version of microcode of CPUID 0x906ec from 0xd2 to 0xd3.
Although Dell might be using the same processor, the motherboard hardware is not
affected and no update will be prepared.

Computrace
==========

When a computer equipped with Computrace is reported stolen, the firmware agent
attempts to notify the monitoring center, allowing the Absolute Theft Recovery Team to
forensically mine the computer using a variety of procedures including key
captures, registry scanning, file scanning, geolocation, and other investigative
techniques to determine who has the computer and how it is being used.
Absolute then works with local law enforcement agencies to recover the computer.

Due to the way the agent works, it's often seen as a "legitimate" firmware implant,
which may be a consideration when purchasing hardware.

The Computrace agent is nonfunctional under Linux and only works when using
Microsoft Windows XP and newer.

The related LoJax UEFI rootkit hijacks the Computrace agent for malicious puposes.

EDK Debug Agent
===============

No production firmware should include the EDK Debug Agent as it allows the end
user to trivially disable host protections like BootGuard, and potentially also
allows unauthenticated access to SMM, which is the most secure layer in the machine.

HP Sure Start
=============

Every time the PC powers on, HP Sure Start automatically validates the integrity
of the BIOS code to help ensure that the PC is safeguarded from malicious attacks.

Once the PC is operational, runtime intrusion detection constantly monitors memory.
In the case of an attack, the PC can self-heal using an isolated "golden copy"
of the BIOS in less than a minute.

HP Sure Start is a hardware technology available only on some HP hardware.

Intel BIOS Guard
================

BIOS guard helps ensure that firmware malware stays out of the BIOS by blocking
all software based attempts to modify protected BIOS without the platform
manufacturer's authorization.

Typically, this is implemented by blocking SMM writes to the SPI flash chip.

Intel Boot Guard
================

Intel Boot Guard is a technology introduced by Intel in the 4th Intel Core
generation (Haswell) to verify the boot process.
This is accomplished by flashing the public key of the BIOS signature into the
write-once field programmable fuses of the CPU itself, typically during the
manufacturing process.

In this way it has the public key of the BIOS and it can verify the correct
signature of the firmware during every subsequent boot.
Once enabled by the manufacturer, Intel Boot Guard cannot be disabled.

Signed Firmware
---------------

Firmware can either be signed or unsigned.
Signed in this context means the binary code has been either signed or encrypted
using private-public asymmetric key cryptography.

It does not include firmware protected with weak symmetric methods such as XTEA as
the private key would need to be stored on the device itself, which is insecure.
It also does not include firmware "protected" with checksums like CRC32.

Devices supporting signed firmware can **only** be updated by the original OEM
and alternate "homebrew" or malicious firmware cannot be written.

Verified Firmware
-----------------

When devices are flashed with new firmware the device will normally self-check that
the data has been written correctly.
Some devices just write new data to an SPI flash chip and hope for the best.

Device Checksums
----------------

When devices are flashed with new firmware the device will normally verify that
the data has been written correctly.
Devices supporting verified firmware either allow the host to read back the written
firmware at a later time, or will return a internally-calculated checksum.

This allows users to verify that devices have not been tampered with, which may
even be a concern before first use due to supply chain attacks.

For UEFI firmware, although the firmware capsule is signed by the OEM or ODM,
software can’t reliably read the SPI EEPROM from userspace.
The UEFI firmware does provide a hash of the firmware, or more specifically,
a hash derived from the stored firmware event log.

A final hash of all the TPM firmware events is stored in the TPM chip as ``PCR0``.

To list the various ``PCRs`` on the running system you can use
``cat /sys/class/tpm/tpm0/pcrs`` for TPMs using protocol 1.2, or
``tpm2_listpcrs`` for TPMs using protocol 2.0.
The PCR0 can be included in the vendor-supplied ``firmware.metainfo.xml`` in the
cabinet archive:

.. code-block:: xml

    <releases>
      <release date="2019-01-08" urgency="high" version="1.2.3">
        <checksum type="sha1" target="device">ce7dd93006be33bcce1a1965cb69634bd0a0fe35</checksum>
        <checksum type="sha256" target="device">c479988947653b403d6a4ebe366cc60eaf7b6e147bd058fb524be418890655c9</checksum>
      </release>
    </releases>

Multiple *golden* device checksums are possible for each system depending on the
specific set up options.
For instance, enabling or disabling Intel TXT would change the system ``PCR0``
checksum.

The device checksums can also be set using the admin console of the LVFS:

.. figure:: img/component-checksums.png
    :align: center
    :width: 100%
    :alt: component checksum

    Adding PCR0 checksums to a component for attestation

Vendor Provenance
-----------------

The LVFS only allows OEMs, ODMs and silicon vendors to upload firmware.
Some OEMs allow the ODM to QA firmware on their behalf and for this reason there
are strictly controlled "affiliate relationships" defined on the LVFS.

Furthermore, the AppStream prefix is checked on upload, to prevent the vendor
trying to replace or inpersonate another vendors legitimate firmware.
This namespacing keeps the OEMs firewalled from each other.

Client side there is another check which verifies the **uploader** of the firmware
has the matching set of restrictions for the USB or PCI-assigned vendor ID.
For instance, Hughski Limited can only deploy firmware onto devices with
``VendorId=USB:0x273F`` and so even if the LVFS account for this company was hacked
they could not update firmware from Logitech or Wacom or instance.

Source URL
----------

All firmware licensed with a GPL-like license must include links to the exact
source release used to build the firmware update.
This claim is only shown for firmware that requires a source URL, although can
be included even for non-open-source firmware if required.

Virus Safe
----------

All firmware uploaded to the LVFS gets scanned by the ClamAV security scanner.
Additionally, when the firmware is no longer embargoed and available to the
public it is uploaded to VirusTotal for further anaysis.
