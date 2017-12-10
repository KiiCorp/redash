#!/bin/sh

set -eu

python /app/redash-setup.py setup --name="${REDASH_ADMIN_NAME}" --email="${REDASH_ADMIN_EMAIL}" --password="${REDASH_ADMIN_PASSWORD}"
exec /app/bin/docker-entrypoint server 
