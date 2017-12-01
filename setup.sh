#!/bin/sh

set -eu

/app/bin/docker-entrypoint create_db
exec /app/bin/docker-entrypoint server
