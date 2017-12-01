#!/usr/bin/env python
#
# Register a default adminstrator for development.

import click
import os
from flask.cli import FlaskGroup
from flask import current_app

from redash import create_app

from sqlalchemy.exc import OperationalError

def create(group):
    app = current_app or create_app()
    return app

@click.group(cls=FlaskGroup, create_app=create)
def cli():
    """Initial script for redash"""

@cli.command()
def bootstrap():
    """Setup with developmnet admin"""
    from redash import models

    isConnected = True
    for i in range(3):
        isConnected = True
        try:
            models.db.engine.connect()
        except OperationalError:
            isConnected = False
        if isConnected:
            break

    if not(isConnected):
        raise RuntimeError("fail to connect db.")

    org_name = 'Development'
    org_slug = 'default'
    user_name = os.getenv('REDASH_ADMIN_NAME', 'Dev Admin')
    user_email = os.getenv('REDASH_ADMIN_EMAIL', 'devad@example.org')
    user_password = os.getenv('REDASH_ADMIN_PASSWORD', 'devad123')

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
    user = models.User(org=default_org, name=user_name, email=user_email,
            group_ids=[admin_group.id, default_group.id])
    user.hash_password(user_password)
    models.db.session.add(user)
    models.db.session.commit()

if __name__ == '__main__':
    cli()
