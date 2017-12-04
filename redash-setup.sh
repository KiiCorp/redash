#!/bin/sh

set -eu

python /app/redash-setup.py wait
/app/bin/docker-entrypoint create_db
nohup /app/bin/docker-entrypoint server >/dev/null 2>&1 &
python /app/redash-setup.py bootstrap
