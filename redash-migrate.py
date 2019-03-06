#!/usr/bin/env python

import json
from time import sleep

from alembic.script import ScriptDirectory
from alembic.migration import MigrationContext

from flask_migrate import stamp, upgrade

from sqlalchemy.exc import OperationalError

from redash import migrate
from redash import create_app
from redash import models

# setup application and db.
app = create_app()
models.db.app = app
isConnected = True
for i in range(6):
    isConnected = True
    try:
        conn = models.db.engine.connect()
    except OperationalError:
        isConnected = False
        if isConnected:
            conn.close()
            break
        sleep(10)
if not(isConnected):
    raise RuntimeError('fail to connect db.')
config = app.extensions['migrate'].migrate.get_config(None)
script = ScriptDirectory.from_config(config)
context = MigrationContext.configure(models.db.engine.connect())

results = models.db.engine.execute("""
SELECT count(table_name) FROM information_schema.tables
WHERE table_name = 'alembic_version';
""")

c = results.first()[0]
if c == 0:
    models.db.create_all()

    # Need to mark current DB as up to date
    with app.app_context():
        stamp()
elif c != 1:
    raise RuntimeError('unexpected table count: %d' % (c))

if script.get_current_head() != context.get_current_revision():
    with app.app_context():
        upgrade()

