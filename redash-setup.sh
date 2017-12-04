#!/bin/sh

set -eu

python /app/redash-setup.py wait
/app/bin/docker-entrypoint create_db
python /app/redash-setup.py bootstrap
exec /app/bin/docker-entrypoint server 
