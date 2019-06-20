FROM centos:7

RUN yum -y update
RUN yum-config-manager --add-repo https://copr.fedorainfracloud.org/coprs/rhughes/lvfs-website/repo/epel-7/rhughes-lvfs-website-epel-7.repo
RUN yum -y install epel-release
RUN yum -y install \
	bsdtar \
	flatpak \
	geolite2-country \
	libgcab1 \
	GeoIP-devel \
	gcc \
	python-GeoIP \
	python36-devel \
	python36-gobject \
	python36-pip \
	python36-psutil
RUN flatpak remote-add --if-not-exists flathub https://flathub.org/repo/flathub.flatpakrepo
RUN flatpak -y install flathub org.freedesktop.fwupd
COPY requirements.txt /tmp/requirements.txt
RUN pip3 install -r /tmp/requirements.txt
RUN mkdir /build
WORKDIR /build
