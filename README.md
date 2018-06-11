Linux Vendor Firmware Service
=============================

This is the website for the Linux Vendor Firmware Service

Missing firmware at LVFS
------------------------

If your device is missing a firmware update that you think should be on LVFS
please file an issue against this project and apply the Github label *missing-firmware*.

Setting up the web service
--------------------------

The official instance is set up using puppet on RHEL 7, on which you could use:

    yum install https://dl.fedoraproject.org/pub/epel/epel-release-latest-7.noarch.rpm
    yum install https://kojipkgs.fedoraproject.org//work/tasks/1429/24421429/libappstream-glib-0.7.5-2.fc28.x86_64.rpm
    yum install https://kojipkgs.fedoraproject.org//packages/gcab/1.0/1.fc27/x86_64/libgcab1-1.0-1.fc27.x86_64.rpm
    yum install https://kojipkgs.fedoraproject.org//packages/python-flask/0.11.1/6.fc27/noarch/python2-flask-0.11.1-6.fc27.noarch.rpm
    yum install https://kojipkgs.fedoraproject.org//packages/python-jinja2/2.9.6/2.fc27/noarch/python2-jinja2-2.9.6-2.fc27.noarch.rpm https://kojipkgs.fedoraproject.org//packages/babel/2.3.4/6.fc27/noarch/python2-babel-2.3.4-6.fc27.noarch.rpm https://kojipkgs.fedoraproject.org//packages/python-markupsafe/0.23/16.fc27/x86_64/python2-markupsafe-0.23-16.fc27.x86_64.rpm
    yum install puppet
    git clone https://github.com/hughsie/lvfs-puppet.git
    cd lvfs-puppet
    hostname admin
    puppet module install puppetlabs-vcsrepo --version 2.2.0
    cp keys.pp.in keys.pp
    vim keys.pp
    puppet apply .

You can set up the database manually using:

    FLASK_APP=app/__init__.py flask-2 initdb
    FLASK_APP=app/__init__.py flask-2 modifydb

## Generating a SSL certificate ##

IMPORTANT: The LVFS needs to be hosted over SSL.
If you want to use LetsEncrypt you can just do `certbot --nginx`.

## Installing the test key ##

Use the test GPG key (with the initial password of `fwupd`).

    gpg2 --homedir=/var/www/lvfs/.gnupg --allow-secret-key-import --import /var/www/lvfs/stable/contrib/fwupd-test-private.key
    gpg2 --homedir=/var/www/lvfs/.gnupg --list-secret-keys
    gpg2 --homedir=/var/www/lvfs/.gnupg --edit-key D64F5C21
    gpg> passwd
    gpg> trust
    gpg> quit

If passwd cannot be run due to being in a sudo session you can do:

    gpg-agent --homedir=/var/www/lvfs/.gnupg --daemon

or

    script /dev/null
    gpg2...

## Using the production key ##

Use the secure GPG key (with the long secret password).

    cd
    gpg2 --homedir=/var/www/lvfs/.gnupg --allow-secret-key-import --import fwupd-secret-signing-key.key
    gpg2 --homedir=/var/www/lvfs/.gnupg --list-secret-keys
    gpg2 --homedir=/var/www/lvfs/.gnupg --edit-key 4538BAC2
      gpg> passwd
      gpg> quit

## Generating metadata for pre-signed firmware ##

If the firmware is already signed with a PKCS-7 or GPG signature and is going
to be shipped out-of-band from the usual LVFS workflow then `local.py` can be
used to generate metadata for `/usr/share/fwupd/remotes.d/vendor/firmware/`.
