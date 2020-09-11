Getting an Account
##################

There is no charge to vendors for the hosting or distribution of content.
You can start the process by emailing richard@hughsie.com with as much information you
have, or just with questions or for more details.

Information to Supply
=====================

* The vendor full legal name
* The public homepage for this vendor
* The domain used for email address assigned to this vendor, e.g. ``@realtek.com,@realtek.com.tw``
* The update protocol are you using, and if it is already supported in fwupd
* Some kind of proof that you have the required permission to upload to the LVFS
* The ``Vendor ID`` for all hardware uploaded by this vendor (from ``fwupdmgr get-devices`` e.g. ``USB:0x046D``)
* The reverse DNS AppStream ID namespace prefix you plan to use for all uploaded firmware, e.g. ``com.hp``
* An assigned "vendor manager" that can create new accounts on the LVFS in the future, and be the primary point of contact
* If you going to be acting as an ODM or IHV to another vendor, e.g. uploading firmware on their behalf

If you are acting as an ODM or IHV to another vendor:

* Which OEM(s) will you be uploading for?
* Do you have a contact person for the OEM? If so, who?
* Will you be QAing the update and pushing to stable yourselves, or letting the OEM do this?

.. note::
  Vendors who can upload firmware updates are in a privileged position where files
  can be installed on end-user systems without authentication.
  This means we have to do careful checks on new requests, which may take a few
  days to complete.

Vendor Groups
=============

On the LVFS there are several classes of user that can be created.
By default users are created as *upload only* which means they can only view
firmware uploaded by themselves.

Users can be *promoted* to QA users by the vendor manager so that they can see
(and optionally modify) other firmware in their vendor group.
QA users are typically the people that push firmware to the testing and stable
remotes.

There can be multiple vendor groups for large OEMs, for instance an OEM might
want a *storage* vendor group that is isolated from the *BIOS* team.
Alternatively, vendors can use Azure to manage users on the LVFS.
Contact the LVFS administrator for more details if you would like to use this.

Adding Users
------------

The vendor manager can add users to an existing vendor group.
If the vendor manager has additional privileges (e.g. the permission to push to stable)
then these can also be set for the new user.

New users have to match the username domain glob, so if the value for the vendor
is ``@realtek.com,@realtek.com.tw`` then ``dave@realtek.com.tw`` could be added by
the vendor manager -- but ``dave@gmail.com`` would be forbidden.

Trusted Users
-------------

Vendor groups are created initially as ``untrusted`` which means no users can
promote firmware to testing and stable.

Once a valid firmware has been uploaded correctly and been approved by someone
in the the LVFS admin team we will *unlock* the user account to the ``trusted``
state which allows users to promote firmware to the public remotes.

.. note::
  In most cases we also need some kind of legal document that shows us that
  the firmware is legally allowed to be redistributed by the LVFS.

  For instance, something like this is usually required:

  *<vendor> is either the sole copyright owner of all uploaded firmware,
  or has permission from the relevant copyright owner(s) to upload files to
  Linux Vendor Firmware Service Project a Series of LF Projects, LLC (known as the “LVFS”)
  for distribution to end users.
  <vendor> gives the LVFS explicit permission to redistribute the
  unmodified firmware binary however required without additional restrictions,
  and permits the LVFS service to analyse the firmware package for any purpose.
  <signature>, <date>, <title>*
