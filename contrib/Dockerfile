FROM centos:7

RUN yum -y update
RUN yum -y install epel-release
RUN yum -y install bsdtar libgcab1 libappstream-glib libstemmer python-flask python-flask-wft python2-flask-login MySQL-python
RUN yum -y install https://kojipkgs.fedoraproject.org//work/tasks/1429/24421429/libappstream-glib-0.7.5-2.fc28.x86_64.rpm
RUN yum -y install https://kojipkgs.fedoraproject.org//packages/gcab/1.0/1.fc27/x86_64/libgcab1-1.0-1.fc27.x86_64.rpm

RUN mkdir /build
WORKDIR /build
