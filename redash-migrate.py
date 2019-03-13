#!/usr/bin/env python

import click
import logging
import os
import json
from time import sleep

from alembic import command
from alembic.script import ScriptDirectory
from alembic.migration import MigrationContext

from flask import current_app
from flask.cli import FlaskGroup
from flask_migrate import stamp, upgrade

from sqlalchemy.exc import OperationalError
from sqlalchemy.exc import SQLAlchemyError


from redash import create_app
from redash import models

# logger = logging.getLogger('redash migrate')
logger = logging.getLogger('redash migrate')

ORG_NAME = 'Development'
ORG_SLUG = 'default'
SHARED_GROUP_NAME = 'shared'
SHARED_DATASOURCE_NAME = 'Shared Data Source'


# setup application and db.
def create(group):
    app = current_app or create_app()
    return app


@click.group(cls=FlaskGroup, create_app=create)
def cli():
    """This is a management script for the wiki application."""

db = None
def get_db():
    global db
    if db != None:
        return db

    models.db.app = current_app
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
    db = models.db
    return db


migration_context = None
def get_migration_context():
    global migration_context
    if migration_context == None:
        migration_context = MigrationContext.configure(get_db().engine.connect())
    return migration_context


default_org = None
def get_default_org():
    global default_org
    if default_org == None:
        org = models.Organization.get_by_slug(ORG_SLUG)
        if org == None:
            return None
        default_org = org
    return default_org


def count_alembic_version_table():
    return get_db().engine.execute("""
    SELECT count(table_name) FROM information_schema.tables
    WHERE table_name = 'alembic_version';
    """).first()[0]


def create_db_migrate():
    count = count_alembic_version_table()
    if count == 0:
        logger.info('create redash tables.')
        get_db().create_all()
    elif count == 1:
        logger.info('redash tables already exist.')
    elif count != 1:
        # this case must not be happened.
        logger.error('unexpected number of alembic_version table: %d' % (count))
        return False

    if get_migration_context().get_current_revision() == None:
        # Need to mark current DB as up to date
        with current_app.app_context():
            stamp()
    else:
        logger.info('revision is already stamped.')

    return True


def create_db_verify():
    count = count_alembic_version_table()
    if count == 0:
        logger.error('redash table does not exists.')
        return False
    elif count == 1:
        logger.info('redash tables already exist.')
    elif count != 1:
        # this case must not be happened.
        logger.error('unexpected number of alembic_version table: %d' % (count))
        return False

    if get_migration_context().get_current_revision() == None:
        logger.error('revision is not stamped')
        return False
    else:
        logger.info('revision is already stamped.')
    return True


def is_latest_revision():
    script = ScriptDirectory.from_config(current_app.extensions['migrate'].migrate.get_config(None))
    context = get_migration_context()

    current = context.get_current_revision()
    head = script.get_current_head()
    if head == current:
        logger.info('db is already latest version: %s' % (head))
        return True
    else:
        logger.info('db will be upgraded to rev %s' % (head))
        return False


def upgrade_db_migrate():
    if not is_latest_revision():
        with current_app.app_context():
            upgrade()
    return True


def upgrade_db_verify():
    return is_latest_revision()


def setup_org_migrate():
    db = get_db()

    # Chech and create primary organization.
    default_org = get_default_org()
    if default_org is None:
        logger.info('create primary organization.')
        default_org = models.Organization(name=ORG_NAME, slug=ORG_SLUG,
                                          settings={})
        db.session.add(default_org)
    else:
        logger.info('primary organization is already exists.')

    # Check and create admin group.
    admin_group = default_org.admin_group
    if admin_group is None:
        logger.info('create admin group.')
        admin_group = models.Group(name='admin',
                                   permissions=['admin', 'super_admin'],
                                   org=default_org,
                                   type=models.Group.BUILTIN_GROUP)
        db.session.add(admin_group)
    else:
        logger.info('admin group is already exists.')

    # Check and create default group.
    default_group = default_org.default_group
    if default_group is None:
        logger.info('create default group.')
        default_group = models.Group(name='default',
                                     permissions=models.Group.DEFAULT_PERMISSIONS,
                                     org=default_org,
                                     type=models.Group.BUILTIN_GROUP)
        db.session.add(default_group)
    else:
        logger.info('default group is already exists.')

    db.session.commit()
    return True

def setup_org_verify():
    # Chech primary organization.
    default_org = get_default_org()
    if default_org is None:
        logger.error('primary organization not found')
        return False
    else:
        logger.info('primary organization is already exists.')

    # Check admin group.
    if default_org.admin_group is None:
        logger.error('admin group not found')
        return False
    else:
        logger.info('admin group is already exists.')

    # Check default group.
    if default_org.default_group is None:
        logger.error('default group not found')
        return False
    else:
        logger.info('default group is already exists.')
    return True


def setup_shared_ds_migrate():
    db = get_db()

    default_org = get_default_org()
    if default_org == None:
        logger.error('shared datasource requires default org but not found.')
        return False

    # Check and create shared group.
    query = models.Group.query.filter(models.Group.name == SHARED_GROUP_NAME,
                                      models.Group.org == default_org)
    count = query.count()
    shared_group = None
    if count == 0:
        shared_group = models.Group(name=SHARED_GROUP_NAME,
                                    permissions=['view_query', 'execute_query'],
                                    org=default_org,
                                    type=models.Group.REGULAR_GROUP)
        db.session.add(shared_group)
    elif count == 1:
        logger.info('shared group is already exists.')
        shared_group = query.one()
    else:
        logger.error('more than one shared data source exists')
        return False

    # Check and create shared data source.
    query = models.DataSource.query.filter(models.DataSource.name == SHARED_DATASOURCE_NAME,
                                           models.DataSource.org == default_org)
    count = query.count()
    if count == 0:
        # Create a shared data source and assign it to admin and shared groups.
        shared_datasource = models.DataSource(org=default_org,
                                              name=SHARED_DATASOURCE_NAME,
                                              type='python',
                                              options={})
        data_source_group_admin = models.DataSourceGroup(
            data_source=shared_datasource,
            group=default_org.admin_group,
            view_only=False)
        data_source_group_shared = models.DataSourceGroup(
            data_source=shared_datasource,
            group=shared_group,
            view_only=True)
        db.session.add_all([shared_datasource, data_source_group_admin, data_source_group_shared])
    elif count == 1:
        logger.info('shared datasource is already exists.')
    else:
        logger.error('more than one shared data source exists: %d' % (count))
        return False

    db.session.commit()
    return True


def setup_shared_ds_verify():
    default_org = get_default_org()
    if default_org == None:
        logger.error('shared datasource requires default org but not found.')
        return False

    # Check and create shared group.
    count = models.Group.query.filter(models.Group.name == SHARED_GROUP_NAME,
                                      models.Group.org == default_org).count()
    if count == 0:
        logger.error('shared group not found.')
        return False
    elif count == 1:
        logger.info('shared group is already exists.')
    else:
        logger.error('more than one shared group exists')
        return False

    # Check and create shared data source.
    count = models.DataSource.query.filter(models.DataSource.name == SHARED_DATASOURCE_NAME,
                                           models.DataSource.org == default_org).count()
    if count == 0:
        logger.error('shared data source not found')
        return False
    elif count == 1:
        logger.info('shared datasource is already exists.')
    else:
        logger.error('more than one shared data source exists: %d' % (count))
        return False

    return True


class admin_info:
    def __init__(self, name, email, password):
        self.name = name
        self.email = email
        self.password = password

def get_admin_info():
    name = os.environ.get("ADMIN_NAME")
    email = os.environ.get("ADMIN_EMAIL")
    password = os.environ.get("ADMIN_PASSWORD")
    if name == None:
        logger.error('environment variable "ADMIN_NAME" required.')
        return None
    if email == None:
        logger.error('environment variable "ADMIN_EMAIL" required.')
        return None
    if password == None:
        logger.error('environment variable "ADMIN_PASSWORD" required.')
        return None
    return admin_info(name, email, password)


def setup_admin_migrate():
    admin = get_admin_info()
    if admin == None:
        return False

    db = get_db()
    default_org = get_default_org()
    if default_org == None:
        logger.error('shared datasource requires default org but not found.')
        return False

    # Check and create an administrator for development.
    count = models.User.query.filter(models.User.email == admin.email, models.User.org == default_org).count()
    if count == 0:
        logger.info('create admin.')
        user = models.User(org=default_org, name=admin.name, email=admin.email,
                           group_ids=[default_org.admin_group.id, default_org.default_group.id])
        user.hash_password(admin.password)
        db.session.add(user)
    elif count == 1:
        logger.info('admin already exists.')
    else:
        logger.error('more than one admin exists: %d' % (c))
        return False
    db.session.commit()
    return True


def setup_admin_verify():
    admin = get_admin_info()
    if admin == None:
        return False

    default_org = get_default_org()
    if default_org == None:
        logger.error('shared datasource requires default org but not found.')
        return False

    # Check and create an administrator for development.
    count = models.User.query.filter(models.User.email == admin.email, models.User.org == default_org).count()
    if count == 0:
        logger.error('admin not found')
        return False
    elif count == 1:
        logger.info('admin already exists.')
    else:
        logger.error('more than one admin exists: %d' % (c))
        return False
    return True


class migration:
    def __init__(self, id, migrater, verifier):
        self.id = id
        self.migrater = migrater
        self.verifier = verifier


migrations = (
    migration('db.create', create_db_migrate, create_db_verify),
    migration('db.upgrade', upgrade_db_migrate, upgrade_db_verify),
    migration('db.setup.org', setup_org_migrate, setup_org_verify),
    migration('db.setup.shared_ds', setup_shared_ds_migrate, setup_shared_ds_verify),
    migration('db.setup.admin', setup_admin_migrate, setup_admin_verify),
)

@cli.command()
def migrate():
    for m in migrations:
        try:
            ok = m.migrater()
            if not ok:
                return False
        except Exception as e:
            logger.error('%s failed. reason: %s', m.id, e)
            return False
    return True

@cli.command()
def verify():
    for m in migrations:
        try:
            ok = m.verifier()
            if not ok:
                return False
        except Exception as e:
            logger.error('%s failed. reason: %s', m.id, e)
            return False
    return True


if __name__ == '__main__':
    cli()

