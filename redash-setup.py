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

def wait():
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

def create_db():
    from redash.models import db
    db.create_all()

    # Need to mark current DB as up to date
    stamp()

def bootstrap(name, email, password):
    from redash import models

    org_name = 'Development'
    org_slug = 'default'

    # Chech and create primary organization.
    default_org = models.Organization.get_by_slug(org_slug)
    if default_org is None:
        default_org = models.Organization(name=org_name, slug=org_slug,
                                          settings={})
        models.db.session.add(default_org)

    # Check and create admin group.
    admin_group = default_org.admin_group
    if admin_group is None:
        admin_group = models.Group(name='admin',
                                   permissions=['admin', 'super_admin'],
                                   org=default_org,
                                   type=models.Group.BUILTIN_GROUP)
        models.db.session.add(admin_group)

    # Check and create default group.
    default_group = default_org.default_group
    if default_group is None:
        default_group = models.Group(name='default',
                                     permissions=models.Group.DEFAULT_PERMISSIONS,
                                     org=default_org,
                                     type=models.Group.BUILTIN_GROUP)
        models.db.session.add(default_group)

    models.db.session.commit()

    # Check and create an administrator for development.
    if models.User.query.filter(models.User.email == email, models.User.org == default_org).count() == 0:
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
    wait()
    create_db()
    bootstrap(name, email, password)

if __name__ == '__main__':
    cli()
