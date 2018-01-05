Linux Vendor Firmware Service
=============================

This is the website for the Linux Vendor Firmware Service

IMPORTANT: This needs to be hosted over SSL, i.e. with a `https://` prefix.

## Using distro packages ##

    yum install https://dl.fedoraproject.org/pub/epel/epel-release-latest-7.noarch.rpm
    yum install \
      cabextract \
      git \
      httpd \
      mariadb-server \
      mod_wsgi \
      MySQL-python \
      python2-boto3 \
      python2-gnupg \
      python2-mysql \
      python-flask \
      python-flask-login \
      python-flask-wtf

Other useful packages might be:
    yum install \
      apachetop \
      certbot-apache \
      iftop \
      mytop

If using RHEL-7 you can get python-flask-login using:

    yum install ftp://fr2.rpmfind.net/linux/fedora/linux/releases/26/Everything/x86_64/os/Packages/p/python-flask-login-0.3.0-6.fc26.noarch.rpm

## Configuring apache ##

Save into `/etc/httpd/conf.modules.d/fwupd.org.conf`

    <VirtualHost *:80>
        ServerName fwupd.org
        Redirect permanent / https://fwupd.org/
    </VirtualHost>

    <VirtualHost _default_:443>
        ServerName fwupd.org
        ServerAlias www.fwupd.org
        ServerAdmin foo@bar.com
        WSGIDaemonProcess lvfs user=lvfs group=lvfs threads=5 python-path=/home/lvfs/lvfs-website
        WSGIScriptAlias / /home/lvfs/lvfs-website/app.wsgi
        WSGIApplicationGroup %{GLOBAL}

        <Directory /home/lvfs/lvfs-website>
            WSGIProcessGroup lvfs
            WSGIApplicationGroup %{GLOBAL}
            Require all granted
        </Directory>
    </VirtualHost>

then `service httpd restart` and `chkconfig httpd on`

## Generating a SSL certificate ##

If you want to use LetsEncrypt you can just do `certbot --apache` -- you may
have to comment out `WSGIScriptAlias` in the `fwupd.org.conf` file to avoid
a warning during install.

## Setting up MariaDB ##

Edit `/etc/my.cnf.d/server.cnf` and add:

    [mysqld]
    max_allowed_packet=60M
    wait_timeout = 6000000
    skip-name-resolve
    max_connect_errors = 1000

## Creating the hosting user? ##

    useradd --create-home lvfs
    passwd lvfs
    usermod -G apache lvfs
    mkdir /home/lvfs/downloads
    mkdir /home/lvfs/.aws
    mkdir /home/lvfs/backup
    chown lvfs:apache /home/lvfs/ -R
    su -l lvfs
    git clone git@github.com:hughsie/lvfs-website.git

Then add something like this to `lvfs-website/app/lvfs.cfg`:

    import os
    DEBUG = True
    PROPAGATE_EXCEPTIONS = False
    SECRET_KEY = 'FIXME'
    HOST_NAME = 'localhost'
    APP_NAME = 'lvfs'
    IP = 'FIXME'
    PORT = 80
    DOWNLOAD_DIR = '/home/lvfs/downloads'
    KEYRING_DIR = '/home/lvfs/.gnupg'
    CABEXTRACT_CMD = '/usr/bin/cabextract'
    CDN_URI = 'https://s3.amazonaws.com/lvfsbucket'
    CDN_BUCKET = 'lvfsbucket'
    DATABASE_HOST = 'localhost'
    DATABASE_USERNAME = 'dbusername'
    DATABASE_PASSWORD = 'dpassword'
    DATABASE_DB = 'lvfs'
    DATABASE_PORT = 3306
    FIRMWARE_BASEURL = 'https://foo.bar/downloads/'
    SESSION_COOKIE_SECURE = True
    REMEMBER_COOKIE_SECURE = True

## Using the CDN ##

Create a `.aws/credentials` file like:

    [default]
    region=us-east-1
    aws_access_key_id=foo
    aws_secret_access_key=bar

## Installing the test key ##

Use the test GPG key (with the initial password of `fwupd`).

    gpg2 --allow-secret-key-import --import fwupd-test-private.key
    gpg2 --list-secret-keys
    gpg2 --edit-key D64F5C21
    gpg> passwd
    gpg> trust
    gpg> quit

If passwd cannot be run due to being in a sudo session you can do:

    script /dev/null
    gpg2...

## Using the production key ##

Use the secure GPG key (with the long secret password).

    cd
    gpg2 --allow-secret-key-import --import fwupd-secret-signing-key.key
    gpg2 --list-secret-keys
    gpg2 --edit-key 4538BAC2
      gpg> passwd
      gpg> quit

## Setting up the database ##

    service mariadb start
    chkconfig mariadb on

    CREATE DATABASE lvfs;
    CREATE USER 'dbusername'@'localhost' IDENTIFIED BY 'dbpassword';
    USE lvfs;
    GRANT ALL ON lvfs.* TO 'dbusername'@'localhost';
    SOURCE schema.sql

The default admin password is `Pa$$w0rd`

## Backing up the database ##

To get just the database you can do:

    mysqldump lvfs > /home/lvfs/backup/lvfs_`date +%Y%m%d`.sql

## Restoring the database from a backup ##

To just restore the database, do:

    mysql
      CREATE DATABASE lvfs;
      use lvfs;
      source backup.sql;

## Enabling backups using cron ##

    crontab -e
    0 0 * * Sun /usr/bin/mysqldump ... > /home/lvfs/backup/lvfs_$( date +"\%Y\%m\%d" ).sql

## Debugging crashes ##

    yum install abrt-cli
    service abrtd start

## Installing extra swap space ##

    fallocate -l 4G /swapfile
    ls -lh /swapfile
    chmod 600 /swapfile
    mkswap /swapfile
    swapon /swapfile
    free -h

## Configuring SSH ##

 * Copy `KexAlgorithms,Ciphers,MACs` from https://wiki.mozilla.org/Security/Guidelines/OpenSSH
 * Set `PasswordAuthentication no`
 * Disable X11 forwarding
 * Use https://observatory.mozilla.org/ to verify SH config

## Setting the system hostname ##

Add this to `/etc/hosts/`
    127.0.0.1       fwupd.org
    127.0.0.1       www.fwupd.org

## Locking down the server ##

 * Disable the rpcbind socket activation: `systemctl disable rpcbind.socket`
 * Disable all networking in MariaDB by adding `skip-networking` to `/etc/my.cnf`


Missing firmware at LVFS
========================
If your device is missing a firmware update that you think should be on LVFS
please file an issue against this project and apply the Github label *missing-firmware*.

