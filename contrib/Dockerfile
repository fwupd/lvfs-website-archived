FROM centos:7

RUN yum -y update
RUN yum -y install epel-release
RUN yum -y install \
	bsdtar \
	libappstream-glib \
	libgcab1 \
	libstemmer \
	python2-pip \
	python2-psutil \
	python2-pylint
RUN yum -y install https://people.freedesktop.org/~hughsient/temp/libappstream-glib-0.7.15-0.643.20181111git.fc29.x86_64.rpm
RUN yum -y install https://kojipkgs.fedoraproject.org//packages/gcab/1.1/1.fc27/x86_64/libgcab1-1.1-1.fc27.x86_64.rpm
COPY requirements.txt /tmp/requirements.txt
RUN pip install -r /tmp/requirements.txt
RUN mkdir /build
WORKDIR /build
