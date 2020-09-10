#!/usr/bin/env bash
echo "Running preboot script"
echo "Executing migrations"
cd /app/www/lvfs
FLASK_APP=lvfs/__init__.py flask db upgrade
