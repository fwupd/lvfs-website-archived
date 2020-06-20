Offline Firmware
################

The `LVFS <https://fwupd.org/lvfs/>`_ is a public webservice designed to allow
OEMs and ODMs to upload firmware easily, and for it to be distributed securely
to tens of millions of end users. For some people, this simply does not work
for various reasons:

* They don't trust the LVFS team, fwupd.org, GPG, certain OEMs or the CDN we use
* They don't want thousands of computers on an internal network downloading all
  the files over and over again
* The internal secure network has no internet connectivity

For these cases there are a few different ways to keep your hardware updated,
in order of simplicity:

Deploy in immutable image
=========================

If the OS is shipped as an image, you can just install the ``.cab`` files into
``/usr/share/fwupd/remotes.d/vendor/firmware`` and then enable ``vendor-directory.conf``
with ``fwupdmgr enable-remote vendor-directory``.

Then once you have disabled the public LVFS using ``fwupdmgr disable-remote lvfs``,
running ``fwupdmgr`` will use only the cabinet archives you deploy in your
immutable image.
Of course, you're deploying a larger image because you might have several unused
firmware files included for each image, but this is how Google Chrome OS is using
fwupd.

Mirror the public firmware
==========================

Using pulp-server
-----------------

You can use `Pulp <https://pulpproject.org/>`_ to mirror the entire *public*
contents of the LVFS (but never private or embargoed firmware).
Create a repo pointing to `PULP_MANIFEST <https://cdn.fwupd.org/downloads/PULP_MANIFEST>`_
and then sync that on a regular basis to download the metadata and firmware.
The contents will not change any more frequently than every 4 hours, so please
use a polling interval of at least that.

Using a helper script
---------------------

There is a helper script `sync-pulp.py <https://github.com/fwupd/lvfs-website/blob/master/contrib/sync-pulp.py>`_
that can be used if ``pulp-server`` is not installed:

.. code-block:: bash

    ./contrib/sync-pulp.py https://cdn.fwupd.org/downloads /mnt/mirror

You can then use a webserver such as Nginx or Apache to export ``/mnt/mirror``
as ``https://my.private.server/mirror``.

Then, disable the LVFS by deleting or modifying ``/etc/fwupd/remotes.d/lvfs.conf``
and then create a ``/etc/fwupd/remotes.d/myprivateserver.conf`` file:

.. code-block:: cfg

    [fwupd Remote]
    Enabled=true
    Type=download
    MetadataURI=https://my.private.server/mirror/firmware.xml.gz
    FirmwareBaseURI=https://my.private.server/mirror

Export a shared directory
=========================

Again, use ``PULP_MANIFEST`` to create a big directory holding all the firmware
(currently ~50GB, but growing), and keep it synced.

Create a NFS or Samba share and export it to clients. Map the folder on each client,
and then create a ``myprivateshare.conf`` file in ``/etc/fwupd/remotes.d``:

.. code-block:: cfg

    [fwupd Remote]
    Enabled=false
    Title=Vendor
    Keyring=none
    MetadataURI=file:///mnt/myprivateshare/fwupd/remotes.d/firmware.xml.gz
    FirmwareBaseURI=file:///mnt/myprivateshare/fwupd/remotes.d

Downloading manually
====================

Download the ``.cab`` files that match your hardware and then install them
on the target hardware via `Ansible <https://www.ansible.com/>`_ or
`Puppet <https://puppet.com/>`_ using ``fwupdmgr install foo.cab``. You can also
use ``fwupdagent get-devices`` to get the existing firmware versions of all
hardware in a format you can parse from scripts.

Create your own LVFS
====================

The LVFS is a free software Python 3 Flask application and an instance can be set up
internally if required. You have to configure much more this way, including
generating your own GPG and PKCS#7 keys, uploading your own firmware and setting
up users and groups on the server.

Doing all this has a few advantages, namely:

* You can upload each firmware file and QA it, only pushing it to stable when ready
* You don't ship firmware which you didn't upload
* You can control the staged deployment, e.g. only allowing the same update to
  be deployed to 1000 servers per day
* You can see failure reports from clients, to verify if the deployment is going well
* You can see nice graphs about how many updates are being deployed across your organisation

However, running a secure LVFS instance is a lot of work as PostgreSQL has to be
used as a database, Redis has to also be set up as a queue manager, and Celery
is used to manage the worker queues.

Although minor versions of the LVFS can be upgraded easily, you should review all
the commits to lvfs-website to ensure that any manual migration is also performed.
