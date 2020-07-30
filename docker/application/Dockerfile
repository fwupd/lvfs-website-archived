FROM centos:8
ARG commit
EXPOSE 5000

RUN dnf -y upgrade
RUN dnf install -y epel-release dnf-plugins-core
RUN dnf config-manager --set-enabled PowerTools epel
RUN dnf group install -y "Development Tools"
RUN dnf -y install \
	GeoIP-devel \
	bsdtar \
	cairo-gobject-devel \
#    clamav \
#    clamav-update \
#    fdupes \
	git \
	gnutls-utils \
	gobject-introspection-devel \
	libgcab1 \
	logrotate \
#    munin \
#    munin-plugins-ruby \
#    munin-node \
	python3-devel \
	python3-pip \
	python3-psutil \
    s3cmd

# create all our dirs
RUN bash -c 'mkdir -p /app/{scripts,conf,logs/uwsgi}'
RUN bash -c 'mkdir -p /data/{downloads,shards,uploads,deleted,firmware}'
RUN bash -c 'mkdir /backups'
WORKDIR /app

# create and activate a venv
ENV VIRTUAL_ENV=/app/venv
RUN python3 -m venv $VIRTUAL_ENV
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

# install all the things
COPY files/requirements.txt /app/conf
RUN pip3 install -r conf/requirements.txt
RUN pip3 install uwsgi

# copy the app; various configs and scripts
COPY scripts/*.sh /app/scripts/
COPY lvfs-website/ /app/www/
COPY files/uwsgi.ini /app/conf/uwsgi.ini
COPY files/flaskapp.cfg /app/www/lvfs/flaskapp.cfg

# cleanup
RUN chown -R nobody:nobody /app /data /backups
RUN dnf group remove -y "Development Tools"

ENTRYPOINT [ "uwsgi", "--ini", "/app/conf/uwsgi.ini" ]
