#!/bin/sh

set -eu

python /app/redash-setup.py wait
/app/bin/docker-entrypoint create_db
/app/bin/docker-entrypoint server &
PID=$!
python /app/redash-setup.py bootstrap
wait $PID
