Custom Protocol
###############

The fwupd project already supports a `huge number of flashing protocols <https://github.com/fwupd/fwupd/tree/master/plugins>`_,
everything from standardized protocols like NMVe, ATA, DFU and also a large number
of *vendor-specfic* protocols like ``logitech_hidpp``, ``synaptics_prometheus`` and ``wacom_raw``.

Most vendors are using a protocol that fwupd already supports, and thus only
need to upload firmware to the LVFS. In the case applying for an account is all that is required.

In the case where the device protocol is a non-compatible variant or a completely
custom protocol then a new fwupd plugin will be required.

.. note::
  It is not possible to upload executable *flasher* code as part of the cabinet
  archive -- only the payload is allowed.

  We will not accecpt non-free executables, static libraries or "shim" layers
  in fwupd. The only way a custom protocol can be supported is by contributing
  a LGPLv2+ plugin upstream.

Some vendors will have the experience to build a plugin themselves, and some vendors
may wish to use a `consulting company <https://fwupd.org/lvfs/docs/consulting>`_
that has the required experience.

These instructons below can either be used by the silicon vendor, or the consulting company
to debug existing and new plugins.
Sometimes new hardware is only supported in the *development* version of fwupd which
may not even be available as a Snap or Flatpak yet.

Prerequisites
=============

* A PC with Linux (preferably the latest version of Fedora) installed bare metal
  (i.e. not in VirtualBox or VMWare)
* Working access to the internet
* A user account (we'll use `emily` as the example here) with administrator permissions

Building fwupd
==============

.. code-block:: bash

    $ cd ~
    $ sudo dnf -y builddep fwupd
    $ sudo dnf -y install tpm2-tss-devel # if using Fedora version less than F32
    $ git clone https://github.com/hughsie/fwupd.git
    $ cd fwupd
    $ mkdir build && cd build
    $ meson ../ --prefix=/home/emily/.root
    $ ninja
    $ ninja install # you can press escape and ignore the permissions dialog
    $ ./src/fwupdtool --verbose get-devices

Using ``fwupdtool``
===================

The fwupd project is split into three main components:

* ``fwupd``: The binary that's running in the background, as root
* ``fwupdmgr``: The client tool that end-users use to interact with the running
  ``fwupd`` binary, as a normal user
* ``fwupdtool``: The debugging tool developers use to find problems and to run
  new code, as root

The ``fwupdtool`` binary does most of the things that ``fwupdmgr`` does, but
without talking to the system ``fwupd`` instance.
It is a lot easier to run ``fwupdtool`` with just one plugin (e.g. ``--plugin-whitelist vli``)
than running the daemon and all the plugins.
You might have to wait 5 seconds and then read thousands of lines of debugging
to see the ``printf()`` you added in a new plugin with the daemon, but with
``./fwupdtool --plugin-whitelist vli --verbose get-devices`` it'll be in a few lines, and instant.

Google actually decided to use ``fwupdtool`` in ChromeOS rather than having a
daemon process running all the time which is why it used to be a *not-installed-by-default*
debug-tool and now is installed into ``/usr/libexec/fwupd/`` and has translations.


To get the list of devices from one specific plugin I would do:

.. code-block:: bash

    sudo /usr/libexec/fwupd/fwupdtool --plugin-whitelist vli get-devices --verbose
    this outputs lots of text onto the console like:
    10:51:49:0584 FuMain               Lenovo ThinkPad WS Dock
     DeviceId:             73ef80b60058b4f18549921520bfd94eaf18710a
     Guid:                 dd1f77bd-88ef-5293-9e34-1fe5ce187658 <- USB\VID_17EF&PID_305A&REV_5011
     Guid:                 1c09a12d-e58a-5b4d-84af-ee3eb4c3c68b <- USB\VID_17EF&PID_305A
     Guid:                 6201fecc-1641-51f6-a6d2-38a06d5476bf <- VLI_USBHUB\SPI_C220
     Guid:                 c9caa540-6e27-5d40-a322-47eaeef84df0 <- USB\VID_17EF&PID_305A&SPI_C220&REV_5011
     Guid:                 cfa1e12c-4eb9-5338-8b23-02acc5423ccb <- USB\VID_17EF&PID_305A&SPI_C220
     Summary:              USB 3.x Hub
     Plugin:               vli
     Protocol:             com.vli.usbhub
     Flags:                updatable|registered|can-verify|can-verify-image
     Vendor:               LENOVO
     VendorId:             USB:0x17EF
     Version:              50.11
     VersionFormat:        bcd
     Icon:                 audio-card
     InstallDuration:      10
     Created:              2019-12-20

We could then install the **raw** firmware blob (i.e. not the cabinet archive
with metadata) on the device using:

.. code-block:: bash

    sudo /usr/libexec/fwupd/fwupdtool --verbose --plugin-whitelist vli \
     install-blob /home/emily/the-firmware.bin 73ef80b60058b4f18549921520bfd94eaf18710a

Firmware Parsing
****************

You can also parse the raw ``.bin`` files using ``fwupdtool`` which has access to all
the available firmware parsers built into all plugins.
For example:

.. code-block:: bash

    sudo ./src/fwupdtool firmware-parse /home/emily/VL105_APP6_8C_09_08_06_20190815.bin
    Choose a firmware type:
    0. Cancel
    1. conexant
    2. 8bitdo
    3. synaprom
    4. rmi
    5. wacom
    6. vli-pd
    7. raw
    8. altos
    9. srec
    10. ihex
    11. vli-usbhub
    12. vli-usbhub-pd
    12<enter>
    FuVliUsbhubPdFirmware:
    Version:                 140.9.8.6
    ChipId:                  VL105
    VID:                     0x2109
    PID:                     0x105
     FuFirmwareImage:
     Data:                  0xc000

Using ``fwupdmgr``
==================

You can perform the end-to-end tests using a local version of fwupd by first
calling `ninja install` to get the new plugin installed.
Then you'll need two terminals open. In the first do:

.. code-block:: bash

    ./src/fwupd --verbose

and in the second you can do:

.. code-block:: bash

    ./src/fwupdmgr install VL105.cab

This will send the firmware archive from the locally built fwupdmgr to the locally
built daemon using a file descriptor, which will call the new plugin code with
the firmware blob in the archive.
The daemon terminal will also show lots of useful debugging during this process.
