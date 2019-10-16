#!/usr/bin/env python

import click
import logging
import os
import json
import sys
from time import sleep
import traceback


from alembic import command
from alembic.script import ScriptDirectory
from alembic.migration import MigrationContext

from flask import current_app
from flask.cli import FlaskGroup
from flask_migrate import stamp, upgrade

from sqlalchemy.exc import OperationalError
from sqlalchemy.exc import SQLAlchemyError

from redash import create_app, models, settings

logger = logging.getLogger(__name__)

ORG_NAME = 'Development'
ORG_SLUG = 'default'
SHARED_GROUP_NAME = 'shared'
SHARED_DATASOURCE_NAME = 'Shared Data Source'
CROSSING_OVER_TENANTS_DATASOURCE_NAME = 'Crossing Over Tenants'

def reset_logging():
    output = "ext://sys.stdout" if settings.LOG_STDOUT else "ext://sys.stderr"
    logging.config.dictConfig({
        "version": 1,
        "formatters": {
            "f1": {
                "format": settings.LOG_FORMAT,
            },
        },
        "handlers": {
            "h1": {
                "class": "logging.StreamHandler",
                "level": settings.LOG_LEVEL,
                "formatter": "f1",
                "stream": output,
            }
        },
        "root": {
            "level": settings.LOG_LEVEL,
            "handlers": ["h1"]
        }})


# setup application and db.
def create(group):
    app = current_app or create_app()
    return app


@click.group(cls=FlaskGroup, create_app=create)
def cli():
    """This is a management script for the wiki application."""

def setup_db():
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


def get_migration_context():
    return MigrationContext.configure(models.db.engine.connect())


def get_default_org():
    return models.Organization.get_by_slug(ORG_SLUG)


def count_alembic_version_table():
    return models.db.engine.execute("""
    SELECT count(table_name) FROM information_schema.tables
    WHERE table_name = 'alembic_version';
    """).first()[0]


def create_db_migrate():
    count = count_alembic_version_table()
    if count == 0:
        logger.info('create redash tables.')
        models.db.create_all()
    elif count == 1:
        logger.info('redash tables already exist.')
    elif count != 1:
        # this case must not be happened.
        raise Exception('unexpected number of alembic_version table: %d' % (count))

    if get_migration_context().get_current_revision() == None:
        # Need to mark current DB as up to date
        with current_app.app_context():
            stamp()
            # stamp() changes logging configuration. To display logs, reset logging configuration.
            reset_logging()
    else:
        logger.info('revision is already stamped.')


def create_db_verify():
    count = count_alembic_version_table()
    if count == 0:
        raise Exception('redash table not found.')
    elif count == 1:
        logger.info('redash tables exist.')
    elif count != 1:
        # this case must not be happened.
        raise Exception('unexpected number of alembic_version table: %d' % (count))

    if get_migration_context().get_current_revision() == None:
        raise Exception('revision is not stamped')
    else:
        logger.info('revision is already stamped.')


def get_current_and_head():
    script = ScriptDirectory.from_config(current_app.extensions['migrate'].migrate.get_config(None))
    context = get_migration_context()

    return context.get_current_revision(), script.get_current_head()


def upgrade_db_migrate():
    current, head = get_current_and_head()
    if head == current:
        logger.info('db is already latest version: %s' % (head))
    else:
        logger.info('db will be upgraded to rev %s' % (head))
        with current_app.app_context():
            upgrade()
            # upgrade() changes logging configuration. To display logs, reset logging configuration.
            reset_logging()


def upgrade_db_verify():
    current, head = get_current_and_head()
    if head == current:
        logger.info('db is already latest version: %s' % (head))
    else:
        raise Exception('db should be upgraded to rev %s' % (head))


def setup_org_migrate():
    db = models.db

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


def setup_org_verify():
    # Chech primary organization.
    default_org = get_default_org()
    if default_org is None:
        raise Exception('primary organization not found')
    else:
        logger.info('primary organization is already exists.')

    # Check admin group.
    if default_org.admin_group is None:
        raise Exception('admin group not found')
    else:
        logger.info('admin group is already exists.')

    # Check default group.
    if default_org.default_group is None:
        raise Exception('default group not found')
    else:
        logger.info('default group is already exists.')


def setup_shared_ds_migrate():
    db = models.db

    default_org = get_default_org()
    if default_org == None:
        raise Exception('shared datasource requires default org but not found.')

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
        raise Exception('more than one shared data source exists')

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
        raise Exception('more than one shared data source exists: %d' % (count))

    db.session.commit()


def setup_shared_ds_verify():
    default_org = get_default_org()
    if default_org == None:
        raise Exception('shared datasource requires default org but not found.')

    # Check and create shared group.
    count = models.Group.query.filter(models.Group.name == SHARED_GROUP_NAME,
                                      models.Group.org == default_org).count()
    if count == 0:
        raise Exception('shared group not found.')
    elif count == 1:
        logger.info('shared group is already exists.')
    else:
        raise Exception('more than one shared group exists')

    # Check and create shared data source.
    count = models.DataSource.query.filter(models.DataSource.name == SHARED_DATASOURCE_NAME,
                                           models.DataSource.org == default_org).count()
    if count == 0:
        raise Exception('shared data source not found')
    elif count == 1:
        logger.info('shared datasource is already exists.')
    else:
        raise Exception('more than one shared data source exists: %d' % (count))


def setup_crossing_over_tenants_ds_migrate():
    db = models.db

    default_org = get_default_org()
    if default_org == None:
        raise Exception('Crossing Over Tenants Data Source requires default org but not found.')

    # Get shared group.
    query = models.Group.query.filter(models.Group.name == SHARED_GROUP_NAME,
                                      models.Group.org == default_org)
    count = query.count()
    shared_group = None
    if count == 0:
        raise Exception('shared group must exist before creating crossing over tenants datasource')
    elif count != 1:
        raise Exception('more than one shared group exists')
    else:
        shared_group = query.one()

    # Check and create crossing over tenants datasource.
    count = models.DataSource.query.filter(models.DataSource.name == CROSSING_OVER_TENANTS_DATASOURCE_NAME,
                                           models.DataSource.org == default_org).count()
    if count == 0:
        # Create an crossing over tenants data source and assign it to shared group with read only permission.
        crossing_over_tenants_datasource = models.DataSource(org=default_org,
                                                   name=CROSSING_OVER_TENANTS_DATASOURCE_NAME,
                                                   type='pg',
                                                   options={})
        datasource_group = models.DataSourceGroup(data_source=crossing_over_tenants_datasource,
                                                  group=shared_group,
                                                  view_only=True)
        db.session.add_all([crossing_over_tenants_datasource, datasource_group])
    elif count == 1:
        logger.info('crossing over tenants datasource already exists')
    else:
        raise Exception('more than one crossing over tenants group exists')

    db.session.commit()


def setup_crossing_over_tenants_ds_verify():
    default_org = get_default_org()
    if default_org == None:
        raise Exception('Crossing Over Tenants Data Source requires default org but not found.')

    # Check create crossing over tenants datasource.
    count = models.DataSource.query.filter(models.DataSource.name == CROSSING_OVER_TENANTS_DATASOURCE_NAME,
                                           models.DataSource.org == default_org).count()
    if count == 0:
        raise Exception('crossing over tenants datasource not found')
    elif count == 1:
        logger.info('crossing over tenants datasource already exists')
    else:
        raise Exception('more than one crossing over tenants group exists')


def setup_admin_migrate():
    name = os.environ.get("VARANUS_REDASH_ADMIN_NAME")
    email = os.environ.get("VARANUS_REDASH_ADMIN_EMAIL")
    password = os.environ.get("VARANUS_REDASH_ADMIN_PASSWORD")
    if name == None:
        raise Exception('environment variable "VARANUS_REDASH_ADMIN_NAME" required.')
    if email == None:
        raise Exception('environment variable "VARANUS_REDASH_ADMIN_EMAIL" required.')
    if password == None:
        raise Exception('environment variable "VARANUS_REDASH_ADMIN_PASSWORD" required.')

    db = models.db
    default_org = get_default_org()
    if default_org == None:
        raise Exception('admin requires default org but not found.')

    # Check and create an administrator for development.
    count = models.User.query.filter(models.User.email == email, models.User.org == default_org).count()
    if count == 0:
        logger.info('create admin.')
        user = models.User(org=default_org, name=name, email=unicode(email),
                           group_ids=[default_org.admin_group.id, default_org.default_group.id])
        user.hash_password(password)
        db.session.add(user)
    elif count == 1:
        logger.info('admin already exists.')
    else:
        raise Exception('more than one admin exists: %d' % (c))
    db.session.commit()


def setup_admin_verify():
    name = os.environ.get("VARANUS_REDASH_ADMIN_NAME")
    email = os.environ.get("VARANUS_REDASH_ADMIN_EMAIL")
    password = os.environ.get("VARANUS_REDASH_ADMIN_PASSWORD")
    if name == None:
        raise Exception('environment variable "VARANUS_REDASH_ADMIN_NAME" required.')
    if email == None:
        raise Exception('environment variable "VARANUS_REDASH_ADMIN_EMAIL" required.')
    if password == None:
        raise Exception('environment variable "VARANUS_REDASH_ADMIN_PASSWORD" required.')

    default_org = get_default_org()
    if default_org == None:
        raise Exception('admin requires default org but not found.')

    # Check an administrator for development.
    admin = models.User.get_by_email_and_org(email, default_org)
    if admin == None:
        raise Exception('admin not found.')
    if admin.name != name:
        raise Exception('admin name is "%s" but "%s".' % (admin.name, name))
    if not admin.verify_password(password):
        raise Exception('admin password is unmatched.')


def check_precondition():
    if os.getenv('REDASH_SECRET_KEY') == None:
        raise Exception('environment variable "REDASH_SECRET_KEY" required.')


class migration:
    def __init__(self, id, migrater, verifier):
        self.id = id
        self.migrater = migrater
        self.verifier = verifier


migrations = (
    migration('db.precondition', check_precondition, check_precondition),
    migration('db.create', create_db_migrate, create_db_verify),
    migration('db.upgrade', upgrade_db_migrate, upgrade_db_verify),
    migration('db.setup.org', setup_org_migrate, setup_org_verify),
    migration('db.setup.shared_ds', setup_shared_ds_migrate, setup_shared_ds_verify),
    migration('db.setup.crossing_over_tenants_ds', setup_crossing_over_tenants_ds_migrate, setup_crossing_over_tenants_ds_verify),
    migration('db.setup.admin', setup_admin_migrate, setup_admin_verify),
)


@cli.command()
@click.option('--exclude', help="exclude migration's ID, comma separated", default=None)
@click.option('--include', help="include migration's ID, comma separated", default=None)
def migrate(exclude, include):
    """
    Verification tool for varanus redash.

    Please refer 'DB Migration and Verification with docker endpoint' in varanus redash github wiki page.
    """

    setup_db()
    global logger
    excludes = []
    if exclude != None:
        excludes = exclude.split(',')
    includes = []
    if include != None:
        includes = include.split(',')
    for m in migrations:
        try:
            logger = logging.getLogger('redash.migrate.' + m.id)
            if m.id in excludes:
                logger.info('this migration is skipped by "exclude" option.')
                continue
            if len(includes) > 0:
                if m.id not in includes:
                    logger.info('this migration is skipped by "include" option.')
                    continue
            m.migrater()
        except Exception as e:
            traceback.print_exc()
            sys.exit(1)
    logger = logging.getLogger('redash.migrate')
    logger.info('completed successfully.')
    sys.exit(0)


@cli.command()
@click.option('--exclude', help="exclude migration's ID, comma separated", default=None)
@click.option('--include', help="include migration's ID, comma separated", default=None)
def verify(exclude, include):
    """
    Migration tool for varanus redash.

    Please refer 'DB Migration and Verification with docker endpoint' in varanus redash github wiki page.
    """

    setup_db()
    global logger
    excludes = []
    if exclude != None:
        excludes = exclude.split(',')
    includes = []
    if include != None:
        includes = include.split(',')
    for m in migrations:
        try:
            logger = logging.getLogger('redash.verify.' + m.id)
            if m.id in excludes:
                logger.info('this verification is skipped by "exclude" option.')
                continue
            if len(includes) > 0:
                if m.id not in includes:
                    logger.info('this migration is skipped by "include" option.')
                    continue
            m.verifier()
        except Exception as e:
            logger.error('%s failed. reason: %s', m.id, e)
            sys.exit(1)
    logger = logging.getLogger('redash.verify')    
    logger.info('completed successfully.')
    sys.exit(0)


if __name__ == '__main__':
    cli()
