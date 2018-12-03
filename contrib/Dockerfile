FROM centos:7

RUN yum -y update
RUN yum -y install epel-release
RUN yum -y install \
	bsdtar \
	libappstream-glib \
	libgcab1 \
	libstemmer \
	MySQL-python \
	python2-flask-login \
	python2-flask-migrate \
	python2-gnupg \
	python2-pylint \
	python-blinker \
	python-humanize \
	python-lxml \
	python-requests \
	python-sqlalchemy \
	python-flask \
	python-flask-sqlalchemy \
	python-flask-wft
RUN yum -y install https://people.freedesktop.org/~hughsient/temp/libappstream-glib-0.7.15-0.643.20181111git.fc29.x86_64.rpm
RUN yum -y install https://kojipkgs.fedoraproject.org//packages/gcab/1.1/1.fc27/x86_64/libgcab1-1.1-1.fc27.x86_64.rpm
RUN yum -y install https://kojipkgs.fedoraproject.org//packages/python-flask/0.11.1/6.fc27/noarch/python2-flask-0.11.1-6.fc27.noarch.rpm
RUN yum -y install https://kojipkgs.fedoraproject.org//packages/python-flask-mail/0.9.1/2.fc27/noarch/python2-flask-mail-0.9.1-2.fc27.noarch.rpm
RUN yum -y install https://people.freedesktop.org/~hughsient/temp/python2-flask_oauthlib-0.9.4-1.fc28.noarch.rpm

RUN mkdir /build
WORKDIR /build
