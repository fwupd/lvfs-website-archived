# Copyright (C) 2019 Richard Hughes <richard@hughsie.com>
# SPDX-License-Identifier: GPL-2.0+

VENV=./env
PYTHON=$(VENV)/bin/python
PYTEST=$(VENV)/bin/pytest
SPHINX_BUILD=$(VENV)/bin/sphinx-build
FLASK=$(VENV)/bin/flask

setup: requirements.txt
	virtualenv ./env
	$(VENV)/bin/pip install -r requirements.txt

clean:
	rm -rf ./build
	rm -rf ./htmlcov

run:
	$(VENV)/bin/python ./app.wsgi
	#FLASK_DEBUG=1

dbup:
	FLASK_APP=lvfs/__init__.py $(FLASK) db upgrade

dbdown:
	FLASK_APP=lvfs/__init__.py $(FLASK) db downgrade

dbmigrate:
	FLASK_APP=lvfs/__init__.py $(FLASK) db migrate

docs:
	$(SPHINX_BUILD) docs build

check: $(PYTEST) contrib/blocklist.cab contrib/chipsec.cab
	$(PYTEST) \
		--cov=lvfs \
		--cov=pkgversion \
		--cov=infparser \
		--cov=cabarchive \
		--cov=plugins \
		--cov-report=html
	$(PYTHON) ./pylint_test.py
