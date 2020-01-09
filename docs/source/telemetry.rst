User Telemetry
##############

By allowing fwupd to *phone home* after attempting a firmware update,
it allows the hardware vendor that uploaded firmware know there are
problems straight  away, rather than waiting for frustrated users to file bugs.

The report containd information that identifies the machine and
old/new firmware versions, and in the event of an error, enough debug
information to actually be useful.
It obviously involve sending the users IP address to the server too.

We have to be exceptionally careful with users privacy and trust.
We cannot just enable automated collection, and this document outlines what
we implemented for fwupd >= 1.0.4.
This functionality should be acceptable to even the most paranoid of users.

The ``fwupd`` daemon stores the result of each attempted update in a local SQLite
database.
In the event there is a firmware update that has been attempted, we now ask the
user if they would like to upload this information to the LVFS.
Using GNOME this would just be a slider in the control center privacy panel,
although this feature is currently unimplemented.

If the user is using the ``fwupdmgr`` tool this is what it shows:

::

    $ fwupdmgr report-history
    Target:                  https://the-lvfs-server/lvfs/firmware/report
    Payload:                 {
                             "ReportVersion" : 1,
                             "MachineId" : "9c43dd393922b7edc16cb4d9a36ac01e66abc532db4a4c081f911f43faa89337",
                             "DistroId" : "fedora",
                             "DistroVersion" : "27",
                             "DistroVariant" : "workstation",
                             "Reports" : [
                               {
                                 "DeviceId" : "da145204b296610b0239a4a365f7f96a9423d513",
                                 "Checksum" : "d0d33e760ab6eeed6f11b9f9bd7e83820b29e970",
                                 "UpdateState" : 2,
                                 "Guid" : "77d843f7-682c-57e8-8e29-584f5b4f52a1",
                                 "FwupdVersion" : "1.0.4",
                                 "Plugin" : "unifying",
                                 "Version" : "RQR12.05_B0028",
                                 "VersionNew" : "RQR12.07_B0029",
                                 "Flags" : 674,
                                 "Created" : 1515507267,
                                 "Modified" : 1515507956
                               }
                             ]
                           }
    Proceed with upload? [Y|n]:

Using this new information that the user volunteers, we display a few new
sections in the LVFS web-console:

.. figure:: img/report-fw.png
    :align: center
    :width: 100%
    :alt: report

    Firmware view showing the report

Which expands out to the report below:

.. figure:: img/report-details.png
    :align: center
    :width: 100%
    :alt: report details

    Report details

This means vendors using the LVFS know the approximate number of success and
failures, and can add different tests to existing QA tests accordingly.
This allows the LVFS to offer the same kind of staged deployment that Microsoft
Update does, where you can limit the number of updated machines to 10,000/day
or automatically pause the specific firmware deployment if > 1% of the reports
come back with failures. These advanced features are disabled by default.

.. figure:: img/telemetry-limits.png
    :align: center
    :width: 100%
    :alt: telemetry limits

    Firmware limits

Some key points:

* We do not share the IP address with the vendor, and it is not even saved in
  the SQLite database
* The ``MachineId`` is a salted hash of the machine ``/etc/machine-id``
* The LVFS does not store reports for firmware that it did not sign itself,
  i.e. locally built firmware archives will be ignored and not logged

The user can disable the reporting functionality in all applications by
editing ``/etc/fwupd/remotes.d/*.conf``

Vendor Summary
==============

Using firmware telemetry overview a vendor can see all the success and
failure reports for all the firmware uploaded to their vendor:

.. figure:: img/telemetry-vendor.png
    :align: center
    :width: 100%
    :alt: vendor telemetry

    Telemetry of all firmware

Until more people are running the latest fwupd and volunteering to share their
update history it is less useful, but still interesting until then.

Known Issues
============

Known issues are problems we know about, and that can be triaged automatically
on the LVFS.
Of course, firmware updates should not ever fail, but in the real world they do,
Of all the failures logged on the LVFS, 95% fall into about 3 or 4 different
failure causes, and if we know hundreds of people are hitting an issue we
already understand we can provide them with some help.

A good example here is the user not being on AC power when rebooting, which
causes a failure, albeit transient and non-fatal.
Another example is if the user tries to do the update with an incorrect system
configuration, for instance a missing ``/boot/efi`` partition.

.. figure:: img/known-issue.png
    :align: center
    :width: 100%
    :alt: known issue

    Notifying the user about known issues

The URL for the user to click on is the result of a rule engine being included
in the LVFS.
Users on the LVFS with the appropriate permissions can also create and view
rules for firmware owned by just their vendor group:

.. figure:: img/issue-conditions.png
    :align: center
    :width: 100%
    :alt: issue conditions

    Issue conditions

.. figure:: img/issue-details.png
    :align: center
    :width: 100%
    :alt: issue details

    Issue details

.. figure:: img/issues-all.png
    :align: center
    :width: 100%
    :alt: all issues

    All issues
