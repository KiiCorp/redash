#!/usr/bin/env python
#
# Register a default adminstrator for development.

import click
import os
from flask.cli import FlaskGroup
from flask import current_app
from flask_migrate import stamp

from redash import create_app

from sqlalchemy.exc import OperationalError

from time import sleep

def create(group):
    app = current_app or create_app()
    return app

@click.group(cls=FlaskGroup, create_app=create)
def cli():
    """Initial script for redash"""

@cli.command()
def wait():
    """Wait other services up"""
    wait2()

def wait2():
    from redash import models

    isConnected = True
    for i in range(3):
        isConnected = True
        try:
            conn = models.db.engine.connect()
        except OperationalError:
            isConnected = False
        if isConnected:
            conn.close()
            break
        sleep(5)

    if not(isConnected):
        raise RuntimeError("fail to connect db.")

@cli.command()
def create_db():
    """Create database"""
    create_db2()

def create_db2():
    from redash.models import db
    db.create_all()

    # Need to mark current DB as up to date
    stamp()

@cli.command()
def bootstrap():
    """Setup with developmnet admin"""

    user_name = os.getenv('REDASH_ADMIN_NAME', 'Dev Admin')
    user_email = os.getenv('REDASH_ADMIN_EMAIL', 'devad@example.org')
    user_password = os.getenv('REDASH_ADMIN_PASSWORD', 'devad123')
    bootstrap2(user_name, user_email, user_password)

def bootstrap2(name, email, password):
    from redash import models

    org_name = 'Development'
    org_slug = 'default'

    # Create primary organization and groups: admin and default.
    default_org = models.Organization(name=org_name, slug=org_slug,
            settings={})
    admin_group = models.Group(name='admin',
            permissions=['admin', 'super_admin'], org=default_org,
            type=models.Group.BUILTIN_GROUP)
    default_group = models.Group(name='default',
            permissions=models.Group.DEFAULT_PERMISSIONS, org=default_org,
            type=models.Group.BUILTIN_GROUP)
    models.db.session.add_all([default_org, admin_group, default_group])
    models.db.session.commit()

    # Create an administrator for development.
    user = models.User(org=default_org, name=name, email=email,
            group_ids=[admin_group.id, default_group.id])
    user.hash_password(password)
    models.db.session.add(user)
    models.db.session.commit()

@cli.command()
@click.option('--name')
@click.option('--email')
@click.option('--password')
def setup(name, email, password):
    wait2()
    create_db2()
    bootstrap2(name, email, password)

if __name__ == '__main__':
    cli()
