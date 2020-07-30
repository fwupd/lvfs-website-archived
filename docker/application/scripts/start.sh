#!/usr/bin/env bash
#set -e

#echo "Executing preboot"
#. /app/scripts/preboot.sh

echo "Starting uwsgi...."
uwsgi --ini /app/conf/uwsgi.ini
