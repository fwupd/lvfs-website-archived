.. image:: img/banner.png
    :align: center
    :width: 70%
    :alt: banner logo

Introduction
############

Updating firmware on devices is traditionally difficult for users on Linux systems.
Not knowing exact hardware details, where to look for updates or how to run the
Windows-specific flashing tools makes it almost impossible to update firmware on
devices.

As a result, *“broken”* hardware is being returned to the vendor and customer
systems are left in an insecure state even when updates have been released that
fix the specific issues. Linux as the OS is now mainstream and vendors need to
support these customers.

The LVFS is a secure web service that can be used by OEM's to upload firmware
archives and can also be used by users to securely download metadata about
available updates and optionally, the updates themselves.
Every month there are over ~50 million files being downloaded from ~10 million clients.

Hundreds of thousands of customer devices are being updated every month thanks to the LVFS!

The Problem
===========

Linux users have traditionally had problems with keeping hardware up to date
with firmware updates.
There are three components to this problem:

* They do not know what exact hardware they have installed, the current
  firmware version, or even if the devices support being upgraded at all.
* They do not know where to look for updates; often searching the various
  vendor websites is an exercise in frustration and as a result most users do not bother.
* Windows-specific flashing tools do not work on Linux; a significant number of
  Linux users keep a Windows virtual machine for essential business-critical
  software that is not available on Linux.
  This will not work for firmware update utilities that require low level hardware access.

The fwupd project can query supported hardware for the current firmware versions
and also deploy new firmware versions to devices, but requires metadata from the
LVFS to know the details about available updates.
It also requires vendors to prepare the firmware with the required metadata and
to use a standardized deployment framework e.g. DFU or UEFI UpdateCapsule.

Using the information from from higher level software centers can show the user the update
description in their own language and offer the update to be installed using
just three clicks of the mouse.
Security updates are handled in the same way as other OS updates meaning it is
just one mechanism for the user to understand.

The LVFS supplies the data in a secure format, allowing the fwupd project to
install the update safely.
Existing approaches have been OEM specific which meant that a large amount of
engineering effort was required, making this approach only financially viable
for enterprise use-cases.

There are a significant number of legal problems with the redistribution of firmware,
and we have been working with vendors finding acceptable methods of redistribution
whilst ensuring confidentially throughout the process. Being backed by a large
Linux vendor with heterogeneous support for many vendors and platforms puts the
LVFS in exactly the right place to build this kind of shared infrastructure.

System Architecture
===================

The architecture is built into three layers: a presentation layer, a mechanism
and a data-provider and each can be replaced as required as they all use standard
protocols.

.. figure:: img/architecture-plan.png
    :align: center
    :width: 100%
    :alt: architecture plan

    Architecture plan, showing each subsystem

GNOME Software
==============

`GNOME Software <https://wiki.gnome.org/Apps/Software>`_ is an application store
designed to make installing, removing and updating both easy and beautiful.
It is available for Linux and used by millions of people on the following
distributions:

* RHEL and CentOS 7.4 or newer
* Fedora 22 or newer
* Ubuntu 16.04 (Xenial) or newer
* Debian 9 (Stretch) or newer
* openSUSE 15.0 or newer
* Arch from 2017-06-13

For most desktop systems, at session start-up the metadata XML and detached
signatures are checked for a specified age, and if required newer files are
automatically downloaded from the LVFS and pushed into fwupd over D-Bus.
When the update list is required we query the fwupd daemon over D-Bus for any
pending updates.
If there are updates that need applying then they are downloaded and the user is
notified and the update details are shown in the specified language.
The user has to explicitly agree to the firmware update action before the update
is performed.

.. figure:: img/gnome-software2.png
    :align: center
    :width: 100%
    :alt: GNOME Software

    GNOME Software

fwupd
=====

This project provides a system-activated daemon ``fwupd`` with a D-Bus interface
that can be used by unprivileged clients.
Clients can perform system wide upgrades and downgrades according to a security
policy, which uses PolicyKit to negotiate for authorization if required.
The command line tool ``fwupdmgr`` can be used to administer headless clients on
the command line over SSH or using a management framework like Red Hat Satellite
or `Dell CCM <https://www.cloudclientmanager.com>`_.

The daemon parses metadata in `AppStream <https://www.freedesktop.org/software/appstream/docs/>`_
format from the LVFS along with a detached GPG or PKCS#7 signature.
The ``.cab`` archives which must contain at least a ``.metainfo.xml`` file and a detached
GPG/PKCS#7 signature of the firmware payload.
Other files are permitted in the archive which allows the same deliverable to be
used for the Windows Update system.

Internally fwupd creates a device with a unique ID, and then a number of
GUIDs are assigned to the device by the provider.
It is these GUIDs specified in the update metadata file that are used to match
a firmware file to a device.
Although it is usually the responsibility of the system vendor to generate a new
GUID if the hardware requires a different firmware file, we can match an update
that only applies to specific versions of hardware using
`CHID <https://docs.microsoft.com/en-us/windows-hardware/drivers/dashboard/using-chids>`_ GUIDs.

The fwupd project ships a number of plugins:

* ``ColorHug``, which supports a custom HID protocol
* ``CSR``, which supports the Cambridge Silicon Radio protocol
* ``Dell``, which supports various devices on Dell hardware
* ``DFU``, which reads and writes data from USB devices supporting the DFU interface
* ``Logitech``, which supports the Unifying protocol
* ``SynapticsMST``, which supports updating MST hardware from Synaptics
* ``Thunderbolt``, which supports Thunderbolt controllers and devices
* ``UEFI``, which reads the
  `ESRT table <https://msdn.microsoft.com/en-us/windows/hardware/drivers/bringup/esrt-table-definition>`_
  and adds devices found on the system and then schedules an offline update to
  run a custom EFI binary
* ``WacomHID``, which supports the Wacom update protocol

Adding more plugins is of course possible, but where possible vendors should use
the existing code and for instance add an ESRT data table when building the
system firmware.

Offline Updates
---------------

When the user agrees to a UEFI firmware update the firmware is unpacked into the
EFI System Partition, several UEFI keys are set and the system reboots.
On reboot the ``fwup.efi`` binary is run before the bootloader is started and
the firmware ``UpdateCapsule`` UEFI runtime source is called.

For most devices (e.g. USB, Thunderbolt, Synaptics, etc.) the update is
performed without requiring a reboot.

LVFS
====

The LVFS provides an OEM-facing website that requires a username and password
to access the secure console.
There is no charge to vendors for the hosting or distribution of content,
although there are some terms of service to vendors distributing content.

This service should only be used to distribute firmware that is flashed onto
non-volatile memory.
It is not designed for firmware that has to be uploaded to devices every time
the device is used.

When ``.cab`` firmware files are submitted the following actions are performed:

#. The update metadata in the archive is checked.
#. The firmware capsule is signed with our GPG key or PKCS#7 certificate.
   Clients **do not** verify the signatures in the catalog file as this is
   for Windows Update only
#. The new cab file is repacked. Only required files are included in the cabinet
   file, typically making the download size much smaller
#. The metadata is added to our database.

Many ODMs are distinct and decoupled from the OEM, and in most cases the ODM is
allowed to upload new firmware but not make it available for users.
For this use case, users on the LVFS can have different attributes, for example:

* Unprivileged users that can upload files to the testing target
* Read only access to all analytics data for a specific vendor
* Quality assurance users that can modify all firmware uploaded to a specific vendor
* Trusted users that can move files to the testing or stable target, and can
  move files from testing to stable
* Manager users that can add new users to an existing vendor

.. figure:: img/user-perms.png
    :align: center
    :width: 100%
    :alt: user permissions

    Admin controlling the user permissions.

Performance
===========

The LVFS runs on a dedicated virtual private server and uses a CDN for the
public metadata.
Every month there are over 50 million files being downloaded from around
10 million unique clients.
About 5% of the firmware downloads are performed using the ``fwupdmgr`` command
line client manually and 95% are done from the GNOME Software GUI program.

There are currently over 160 devices supported on the LVFS with over 400
different firmware versions and the system runs with a measured 99.95% uptime.

Conclusions
===========

The LVFS has grown to be an essential part of the Linux ecosystem and there
are currently 26 vendors using the service, 11 of which are multi-billion
dollar companies.
4,000 **new** clients use the service *every day*, with over 3,000,000
returning users.
The LVFS is a mature service providing important functionality for Linux users.

Future Work
-----------

Various vendors are working on custom plugins for fwupd as they either cannot
retrofit older hardware with the ESRT data table, or because they want more
control over the low level flashing protocol.
We certainly would encourage any new vendors wanting to use the LVFS and fwupd
to use a well-known standard like DFU or UEFI UpdateCapsule with ESRT as it
means there is no application code to write.

From a system administrators point of view, it will also soon be possible to get
notified of updates and perform upgrades using the Cockpit framework as well as
the usual client tools.

Related Projects
----------------

The `Dell Repository Manager <http://www.dell.com/support/article/us/en/04/SLN293301?c=us&l=en&s=bsd&cs=04>`_
allows you to update the firmware on various models of Dell enterprise hardware.
There are several software (e.g. the SSU and SBUU) and hardware elements
specific to Dell (e.g., the LCC or USC) and most of the stack is proprietary.

Microsoft provides a service called `Windows Update <http://windows.microsoft.com/en-gb/windows/windows-update>`_
which takes driver updates from vendors, optionally performs some quality
control on the update, signs the firmware and then hosts the firmware on a CDN.
The entire stack is proprietary and for Microsoft Windows only.
