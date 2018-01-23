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
    yum install https://kojipkgs.fedoraproject.org//work/tasks/4001/24374001/libappstream-glib-0.7.5-1.fc28.x86_64.rpm
    yum install https://kojipkgs.fedoraproject.org//packages/gcab/1.0/1.fc27/x86_64/libgcab1-1.0-1.fc27.x86_64.rpm
    yum install puppet
    hostname admin
    puppet module install puppetlabs-vcsrepo --version 2.2.0
    cp keys.pp.in keys.pp
    vim keys.pp
    puppet apply .

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
