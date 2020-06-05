#!/bin/sh
set -e
set -x

# required for tests
redis-server &

pytest --cov=lvfs --cov=plugins --cov=pkgversion --cov=infparser --cov=cabarchive --cov-fail-under=60
