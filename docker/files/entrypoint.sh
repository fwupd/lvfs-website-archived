#!/bin/bash
set -e

if [ $DEPLOY -eq "application" ]
then
	exec uwsgi --ini /app/conf/uwsgi.ini
fi

if [ $DEPLOY -eq "worker" ]
	exec celery -A lvfs.celery.worker --queues metadata,firmware,celery,yara
fi
