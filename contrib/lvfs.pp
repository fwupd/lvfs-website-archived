file { '/var/www':
    ensure   => 'directory',
}
file { '/var/www/lvfs':
    ensure   => 'directory',
    owner    => 'uwsgi',
    group    => 'uwsgi',
    require  => File['/var/www'],
}
vcsrepo { '/var/www/lvfs/admin':
    ensure   => latest,
    provider => git,
    revision => $lvfs_revision,
    source   => 'https://github.com/hughsie/lvfs-website.git',
    user     => 'uwsgi',
    group    => 'uwsgi',
    require  => [ File['/var/www/lvfs'], Package['uwsgi']],
}
file { '/var/www/lvfs/downloads':
    ensure   => 'directory',
    owner    => 'uwsgi',
    group    => 'uwsgi',
    require  => [ File['/var/www/lvfs'], Package['uwsgi'] ],
}
file { '/var/www/lvfs/.aws':
    ensure   => 'directory',
    owner    => 'uwsgi',
    group    => 'uwsgi',
    require  => [ File['/var/www/lvfs'], Package['uwsgi'] ],
}
file { '/var/www/lvfs/.aws/credentials':
    ensure   => 'present',
    owner    => 'uwsgi',
    group    => 'uwsgi',
    content  => "
[default]
region=us-east-1
aws_access_key_id=${aws_access_key_id}
aws_secret_access_key=${aws_secret_access_key}
",
    require => [ File['/var/www/lvfs'], Package['uwsgi'] ],
}
file { '/var/www/backup':
    ensure  => 'directory',
    owner   => 'uwsgi',
    group   => 'uwsgi',
    require => Package['uwsgi'],
}
file { '/var/www/lvfs/admin/app/custom.cfg':
    ensure  => 'present',
    replace => 'no',
    owner   => 'uwsgi',
    group   => 'uwsgi',
    content => "# Managed by Puppet, DO NOT EDIT
import os
DEBUG = False
PROPAGATE_EXCEPTIONS = True
SECRET_KEY = '${lvfs_secret_key}'
HOST_NAME = 'localhost'
APP_NAME = 'lvfs'
IP = '${server_ip}'
PORT = 80
DOWNLOAD_DIR = '/var/www/lvfs/downloads'
KEYRING_DIR = '/var/www/lvfs/.gnupg'
DATABASE_HOST = 'localhost'
DATABASE_USERNAME = '${dbusername}'
DATABASE_PASSWORD = '${dbpassword}'
DATABASE_DB = 'lvfs'
DATABASE_PORT = 3306
SESSION_COOKIE_SECURE = ${using_ssl}
REMEMBER_COOKIE_SECURE = ${using_ssl}
",
    require => [ File['/var/www/lvfs'], Package['uwsgi'] ],
}

# all the Flask request
package { 'bsdtar':
    ensure => installed,
}
package { 'cabextract':
    ensure => installed,
}
package { 'git':
    ensure => installed,
}
package { 'MySQL-python':
    ensure => installed,
}
package { 'python2-boto3':
    ensure => installed,
}
package { 'python2-gnupg':
    ensure => installed,
}
#package { 'python2-mysql':
#    ensure => installed,
#}
package { 'python-flask':
    ensure => installed,
}
package { 'python2-flask-login':
    ensure => installed,
}
package { 'python-flask-wtf':
    ensure => installed,
}

# set up the database
package { 'mariadb-server':
  ensure => installed,
}
file { '/etc/my.cnf.d/00-lvfs.cnf':
    ensure => "file",
    content => "# Managed by Puppet, DO NOT EDIT
[mysqld]
skip-networking
max_allowed_packet=60M
wait_timeout = 6000000
skip-name-resolve
max_connect_errors = 1000
",
    require => Package['mariadb-server'],
}
cron { 'mysqldump':
    command => '/usr/bin/mysqldump lvfs > /var/www/backup/lvfs_$( date +"\%Y\%m\%d" ).sql',
    user    => 'root',
    weekday => 'Sun',
    hour    => 0,
    minute  => 0,
    require => Package['mariadb-server'],
}
service { 'mariadb':
    ensure => 'running',
    enable => true,
    require => Package['mariadb-server'],
}
file { '/var/lib/mysql/lvfs.sql':
    ensure => "file",
    content => "
CREATE DATABASE lvfs;
CREATE USER '${dbusername}'@'localhost' IDENTIFIED BY '${dbpassword}';
USE lvfs;
GRANT ALL ON lvfs.* TO '${dbusername}'@'localhost';
SOURCE /var/www/lvfs/admin/schema.sql
",
    require => Package['mariadb-server'],
}

# use uWSGI
package { 'uwsgi-plugin-python':
    ensure => installed,
}
package { 'uwsgi':
    ensure => installed,
}
file { '/var/log/uwsgi':
    ensure   => 'directory',
    owner    => 'uwsgi',
    group    => 'uwsgi',
    require  => Package['uwsgi'],
}
file { '/etc/tmpfiles.d/uwsgi.conf':
    ensure => "file",
    content => "D /run/uwsgi 0770 uwsgi uwsgi -",
    require => Package['uwsgi'],
}

file { '/etc/uwsgi.d/lvfs.ini':
    ensure   => "file",
    owner    => 'uwsgi',
    group    => 'uwsgi',
    content => "# Managed by Puppet, DO NOT EDIT
[uwsgi]
chdir = /var/www/lvfs/admin
module = app:app
plugins = python
uid = uwsgi
gid = uwsgi
socket = /run/uwsgi/%n.socket
chmod-socket = 660
logto = /var/log/uwsgi/%n.log
stats = 127.0.0.1:9191
",
    require => Package['uwsgi'],
}
service { 'uwsgi':
    ensure => 'running',
    enable => true,
    require => [ Package['uwsgi'], File['/etc/uwsgi.d/lvfs.ini'] ],
}

exec { 'nginx-uwsgi-membership':
    unless  => '/bin/grep -q "uwsgi\\S*nginx" /etc/group',
    command => '/sbin/usermod -aG uwsgi nginx',
    require => Package['uwsgi'],
}

# start nginx load balancer
package { 'nginx':
    ensure => installed,
}
file { '/etc/nginx/nginx.conf':
    ensure => "file",
    content => "# Managed by Puppet, DO NOT EDIT
user nginx;
worker_processes auto;
error_log /var/log/nginx/error.log;
pid /run/nginx.pid;

events {
    worker_connections 1024;
}

http {
    log_format  main  '\$remote_addr - \$remote_user [\$time_local] \"\$request\" '
                      '\$status \$body_bytes_sent \"\$http_referer\" '
                      '\"\$http_user_agent\" \"\$http_x_forwarded_for\"';

    access_log  /var/log/nginx/access.log  main;

    sendfile            on;
    tcp_nopush          on;
    tcp_nodelay         on;
    keepalive_timeout   65;
    types_hash_max_size 2048;

    include             /etc/nginx/mime.types;
    default_type        application/octet-stream;

    include /etc/nginx/conf.d/*.conf;

    server {
        listen       80 default_server;
        listen       [::]:80 default_server;

        server_name  ${server_fqdn};
        root         /usr/share/nginx/html;
        client_max_body_size 80M;

        # only allow http:// URIs
        if (\$scheme != \"https\") {
            return 301 https://\$host\$request_uri;
        }

        # support SSL using Let's Encrypt
        listen       443 ssl;
        ssl_certificate /etc/letsencrypt/live/${server_fqdn}/fullchain.pem;
        ssl_certificate_key /etc/letsencrypt/live/${server_fqdn}/privkey.pem;
        include /etc/letsencrypt/options-ssl-nginx.conf;
        ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem;

        # Load configuration files for the default server block.
        include /etc/nginx/default.d/*.conf;

        location /img/ {
            alias /var/www/lvfs/admin/app/static/img/;
        }
        location /downloads/firmware.xml.gz {
            alias /var/www/lvfs/downloads/firmware.xml.gz;
        }
        location /downloads/firmware.xml.gz.asc {
            alias /var/www/lvfs/downloads/firmware.xml.gz.asc;
        }
        location / {
            uwsgi_pass unix:///run/uwsgi/lvfs.socket;
            include uwsgi_params;
        }

        error_page 404 /404.html;
            location = /40x.html {
        }

        error_page 500 502 503 504 /50x.html;
            location = /50x.html {
        }
    }
}
",
    require => Package['nginx'],
}
service { 'nginx':
    ensure => 'running',
    enable => true,
    require => [ Package['nginx'], Package['uwsgi'] ],
}

# allow monitoring server
package { 'munin':
    ensure => installed,
}
package { 'munin-ruby-plugins':
    ensure => installed,
}
service { 'munin-node':
    ensure   => 'running',
    enable   => true,
    require  => Package["munin"],
}
package { 'httpd-tools':
    ensure => installed,
}
exec { "munin-htpasswd":
    command     => "/usr/bin/htpasswd -cb /etc/munin/munin-htpasswd ${munin_username} ${munin_password}",
    unless      => "/usr/bin/test -s /etc/munin/munin-htpasswd",
    require     => [ Package["munin"], Package['httpd-tools'] ],
}
file { '/etc/nginx/default.d/munin.conf':
    ensure => "file",
    content => "# Managed by Puppet, DO NOT EDIT
location /munin/static/ {
    alias /etc/munin/static/;
    expires modified +1w;
}

location /munin/ {
    auth_basic Restricted;
    auth_basic_user_file /etc/munin/munin-htpasswd;
    alias /var/www/html/munin/;
    expires modified +310s;
}
",
    require => Package['nginx'],
}

# fixes permissions after a key has been imported
file { '/var/www/lvfs/.gnupg':
    ensure   => 'directory',
    owner    => 'uwsgi',
    group    => 'uwsgi',
    require  => File['/var/www/lvfs'],
}
exec { 'gnupg-uwsgi-chown':
    command  => "/bin/chown -R uwsgi:uwsgi /var/www/lvfs/.gnupg/",
    require  => File['/var/www/lvfs/.gnupg'],
}
