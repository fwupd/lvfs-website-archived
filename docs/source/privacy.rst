Privacy Report
##############

We hold personal data about vendors, administrators, clients and other
individuals for a variety of purposes.
This policy sets out how we seek to protect personal data and ensure that
administrators understand the rules governing their use of personal data to
which they have access in the course of their work.
In particular, this policy requires that the Data Protection Officer (DPO) be
consulted before any significant new data processing activity is initiated to
ensure that relevant compliance steps are addressed.

Scope
-----

This policy applies to all users who have access to any of the personally
identifiable data.

Who is responsible for this policy?
-----------------------------------

As the Data Protection Officer, `Richard Hughes <mailto:richard@hughsie.com>`_.
has overall responsibility for the day-to-day implementation of this policy.
The DPO is registered with the Information Commissioner’s Office (ICO) in the
United Kingdom as a registered data controller.

Fair and lawful processing
--------------------------

We must process personal data fairly and lawfully in accordance with individuals’ rights.
This generally means that we should not process personal data unless the
individual whose details we are processing has consented to this happening,
or where such collection is unavoidable and/or considered pragmatic in the
context, e.g. logging the number of downloads of a particular file.

We do not consider an IP address to represent a single user (due to NAT or VPN use),
and as such metadata requests are not considered personal data using the draft GDPR guidelines.

Accuracy and relevance
----------------------

We will ensure that any personal data we process is accurate, adequate,
relevant and not excessive, given the purpose for which it was obtained.
We will not process personal data obtained for one purpose for any unconnected
purpose unless the individual concerned has agreed to this or would otherwise
reasonably expect this.
Individuals may ask that we correct inaccurate personal data relating to them.
If you believe that information is inaccurate you should inform the DPO.

Your personal data
------------------

You must take reasonable steps to ensure that personal data we hold about
hardware vendors is accurate and updated as required.
For example, if your personal circumstances change, please update them using
the profile pages or inform the Data Protection Officer.

Data security
-------------

We keep personal data secure against loss or misuse.
Where other organisations process personal data as a service on our behalf,
the DPO will establish what, if any, additional specific data security
arrangements need to be implemented in contracts with those third party
organisations.

Storing data securely
*********************

All data is stored electronically.
All documents and code are held on a locked LUKS partition with a password
adhering to security best practices.

Data retention
**************

We must retain personal data for no longer than is necessary.
What is necessary will depend on the circumstances of each case, taking into
account the reasons that the personal data was obtained, but should be
determined in a manner consistent with our data retention guidelines.
Anonymized user data (e.g. metadata requests) will be kept for a maximum of
5 years which allows us to project future service requirements and provide
usage graphs to the vendor.

Transferring data internationally
*********************************

There are restrictions on international transfers of personal data.
We do not transfer personal data anywhere outside the EU without the approval
of the Data Protection Officer, unless required to do so by law.

Subject Access Requests
-----------------------

Please note that under the Data Protection Act 1998, individuals are entitled,
subject to certain exceptions, to request access to information held about them.

On receiving a subject access request, we will refer that request immediately
to the DPO. We may ask you to help us comply with those requests.
Please also contact the Data Protection Officer if you would like to correct
or request information that we hold about you.
There are also restrictions on the information to which you are entitled under
applicable law.

Processing data
---------------

We will never use identifiable vendor data for direct marketing purposes.

GDPR Provisions
-------------------------------------

Where not specified previously in this policy, the following provisions will
be in effect on or before 25 May 2018.

Transparency of data protection
-------------------------------

Being transparent and providing accessible information to individuals about how
we will use their personal data is important for our project.
The following are details on how we collect data and what we will do with it:

Firmware Vendor Information
***************************

* **What:** The hardware vendor name, password, GPG public key and content of original
  uploaded firmware files.
* **Why collected:** Secure authentication, to allow any possible future audit
  and to provide authorised users access to signed firmware files.
* **Where stored:** MySQL database on fwupd.org.
* **When copied:** Backed up to off-site secure LUKS partition weekly.
* **Who has access:** The hardware vendor (filtered by the QA group) and the DPO.
* **Wiped:** When the vendor requests deletion of the user account.

Service Event Log
*****************

* **What:** IP address (unhashed) and REST method requested, along with any error.
* **Why collected:** Providing an event log for checking what the various
  hardware vendors are doing, or trying to do.
* **Where stored:** MySQL database on fwupd.org.
* **When copied:** Backed up to off-site secure LUKS partition weekly.
* **Who has access:** The hardware vendor (filtered by the QA group) and the DPO.
* **Wiped:** When the QA group is deleted.

Firmware Download Log
*********************

* **What:** IP address (hashed), timestamp, filename of firmware, user-agent of client.
* **Why collected:** To know what client versions are being used for download,
  and to provide a download count over time for a specific firmware file.
* **Where stored:** MySQL database on fwupd.org.
* **When copied:** Backed up to off-site secure LUKS partition weekly.
* **Who has access:** The hardware vendor (filtered by the QA group) and the DPO.
* **Wiped:** When the firmware is deleted.

Firmware Reports
****************

* **What:** Machine ID (hashed), failure string and checksum of failing file,
  OS distribution name and version.
* **Why collected:** Allows the hardware vendor to assess if the firmware update
  is working on real hardware.
* **Where stored:** MySQL database on fwupd.org.
* **When copied:** Backed up to off-site secure LUKS partition weekly.
* **Who has access:** The hardware vendor (filtered by the QA group) and the DPO.
* **Wiped:** When the firmware is deleted.

We will ensure any use of personal data is justified using at least one of
the conditions for processing and this had been specifically documented above.

Consent
-------

The data that we collect is subject to active consent by the data subject.
This consent can be revoked at any time.
Revoking consent to use data ends any vendor relationship with the LVFS.

Data portability
----------------

Upon request, a data subject should have the right to receive a copy of their
data in a structured format, typically an SQL export.
These requests should be processed within one month, provided there is no
undue burden and it does not compromise the privacy of other individuals.
A data subject may also request that their data is transferred directly to
another system. This is available for free.

Right to be forgotten
---------------------

A vendor may request that any information held on them is deleted or removed,
and any third parties who process or use that data must also comply with the request.
An erasure request can only be refused if an exemption applies.

Privacy by design and default
-----------------------------

Privacy by design is an approach to projects that promote privacy and data
protection compliance from the start.
The DPO will be responsible for conducting Privacy Impact Assessments and
ensuring that all changes commence with a privacy plan.
When relevant, and when it does not have a negative impact on the data subject,
privacy settings will be set to the most private by default.

Data audit and register
-----------------------

Regular data audits to manage and mitigate risks will inform the data register.
This contains information on what data is held, where it is stored,
how it is used, who is responsible and any further regulations or retention
timescales that may be relevant.

Reporting breaches
------------------

All users of the LVFS have an obligation to report actual or potential data
protection compliance failures. This allows us to:

* Investigate the failure and take remedial steps if necessary
* Maintain a register of compliance failures
* Notify the Supervisory Authority (SA) of any compliance failures that are
  material either in their own right or as part of a pattern of failures

Please refer to the DPO for our reporting procedure.

Monitoring
----------

Everyone who actively uses the LVFS must observe this policy.
The DPO has overall responsibility for this policy.
They will monitor it regularly to make sure it is being adhered to.

Consequences of Failing to Comply
---------------------------------

We take compliance with this policy very seriously.
Failure to comply puts both you and us at risk.
The importance of this policy means that failure to comply with any requirement
may lead to disciplinary action under our procedures.
If you have any questions or concerns about anything in this policy,
do not hesitate to contact the DPO.
