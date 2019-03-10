FROM centos:7

RUN yum -y update
RUN yum -y install epel-release
RUN yum -y install \
	bsdtar \
	geolite2-country \
	gnutls-utils \
	libappstream-glib \
	libgcab1 \
	libstemmer \
	GeoIP-devel \
	gcc \
	python-GeoIP \
	python34-devel \
	python34-gobject \
	python34-pip \
	python34-psutil \
	python34-pylint
RUN yum -y install https://people.freedesktop.org/~hughsient/temp/libappstream-glib-0.7.15-0.646.20190123git.fc29.x86_64.rpm
RUN yum -y install https://kojipkgs.fedoraproject.org//packages/gcab/1.1/1.fc27/x86_64/libgcab1-1.1-1.fc27.x86_64.rpm
COPY requirements.txt /tmp/requirements.txt
RUN pip3 install -r /tmp/requirements.txt
RUN mkdir /build
WORKDIR /build
