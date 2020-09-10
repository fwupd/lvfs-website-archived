#!/bin/bash

# celery worker
./celery-worker.sh -D
status=$?
if [ $status -ne 0 ]; then
	echo "Failed to start celery worker"
	exit $status
fi

# celery beat
./celery-beat.sh -D
status=$?
if [ $status -ne 0 ]; then
	echo "Failed to start celery beat"
	exit $status
fi

# The container health check loop
while sleep 60; do
	"checking for running processes"
	ps aux | grep celery-worker.sh | grep -q -v grep
	WORKER_STATUS=$?
	ps aux | grep celery-beati.sh | grep -q -v grep
	BEAT_STATUS=$?
	if [ $WORKER_STATUS -ne 0 -o $BEAT_STATUS -ne 0 ]; then
		echo "A process has exited."
		exit 1
	fi
done
