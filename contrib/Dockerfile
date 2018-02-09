FROM centos:7

RUN yum -y update
RUN yum -y install epel-release
RUN yum -y install \
	bsdtar \
	libappstream-glib \
	libgcab1 \
	libstemmer \
	MySQL-python \
	python2-boto3 \
	python2-flask-login \
	python2-gnupg \
	python2-pylint \
	python-requests \
	python-sqlalchemy \
	python-flask \
	python-flask-wft
RUN yum -y install https://kojipkgs.fedoraproject.org//packages/libappstream-glib/0.7.6/1.fc27/x86_64/libappstream-glib-0.7.6-1.fc27.x86_64.rpm
RUN yum -y install https://kojipkgs.fedoraproject.org//packages/gcab/1.1/1.fc27/x86_64/libgcab1-1.1-1.fc27.x86_64.rpm
RUN yum -y install https://kojipkgs.fedoraproject.org//packages/python-flask/0.11.1/6.fc27/noarch/python2-flask-0.11.1-6.fc27.noarch.rpm

RUN mkdir /build
WORKDIR /build
