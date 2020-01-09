LVFS Releases
#############

1.1.5 (2019-11-15)
==================

This release adds the following features:

* Add support for matching firmware requirements on device parents
* Allow researchers to run YARA queries on the public firmware
* Allow the blocklist plugin to add persistent claims
* Use PSPTool to parse the AMD PSP section

This release fixes the following bugs:

* Add the Dell PFS as a component shard
* Allow the owner of the firmware to always change update details
* Convert to Blueprints to improve page loading time
* Do not hardcode the list of version formats in various places
* Do not share the shard name between GUIDs
* Only auto-demote stable-to-testing, not testing-to-embargo or stable-to-embargo
* Show the version format versions with no trailing zeros

1.1.4 (2019-09-26)
==================

This release adds the following features:

* Add component issues such as CVEs in a structured way
* Add more OEM notification emails for ODM actions
* Add support for name variant suffixes
* Add vendor namespaces to enforce ODM relationships
* Allow searching for CVEs when logged in
* Allow the OEM to better control what the ODM is able to do

This release fixes the following bugs:

* Allow vendors to optionally disable the inf parsing
* Blacklist generic GUIDs like 'main-system-firmware'
* Check the source and release URLs are valid if provided
* Do not show deleted firmware on the recent list on the dashboard
* Don't auto-demote firmware because of old reports
* Enforce the VersionFormat if the version is an integer
* Fix a crash if uploading a file with a missing metadata_license tag
* Provide a way to un-disable users as a vendor manager
* Regenerate embargo remotes ever 5 minutes
* Use a sane error message on upload when a component drops a GUID

1.1.3 (2019-08-06)
==================

This release adds the following features:

* Show a nag message for admin or manager account without 2FA
* Do not use AppStream-glib to parse the metainfo file
* Automatically demote firmware with more than 5 failures and a success rate of %lt;70%
* Allow firmware or vendors to enable DoNotTrack functionality
* Show the user capabilities in the headerbar
* Protect all forms against CSRF

This release fixes the following bugs:

* Retry all existing tests if the category or protocol is changed
* Do not allow forward slashes in AppStream ID values
* Use a proper AppStream ID for the CHIPSEC shards
* Show flashed messages on the landing page
* Better support firmware requires without conditions or versions
* Do not allow AppStream markup in non description elements

1.1.2 (2019-05-28)
==================

This release adds the following features:

* Add a new plugin to check portable executable files
* Save the shards in an on-disk cache which allows re-running tests
* Add a failure for any firmware that is signed with a 3-year expired certificate
* Add shard certificates to the database and show them in the component view

This release fixes the following bugs:

* Make it easier to enter multiline text as plugin settings

1.1.1 (2019-05-21)
==================

This release adds the following features:

* Allow managers to edit their own list of embargoed countries
* Record the size and entropy of the component shards when parsing
* Analyze Intel ME firmware when it is uploaded

This release fixes the following bugs:

* Do not expect device checksums for ME or EC firmware

1.1.0 (2019-05-14)
==================

This release adds the following features:

* Run CHIPSEC on all UEFI firmware files
* Show details of UEFI firmware volumes for capsule updates
* Show differences between public revisions of firmware
* Provide some extra information about detected firmware shards

This release fixes the following bugs:

* Only decompress the firmware once when running tests
* Make the component detail page a bit less monolithic
* Never leave tests in the running state if a plugin crashes

1.0.0 (2019-05-02)
==================

This release adds the following features:

* Allow the admin to change the AppStream ID or name of components

This release fixes the following bugs:

* Do not allow the telemetry card title to overflow
* Ensure the ``firmware-flashed`` value is a valid lowercase GUID
* Make the component requirements page easier to use
* Do not add duplicate ``<hardware>`` values
* Remove the hard-to-use breadcrumb and use a single back button
