import os
from inspect import ismethod
from redash.utils import mustache_render
from redash.settings.helpers import parse_boolean
import models

import pystache

version = '1.1.0'


def can_query_securely(data_source):
    if not hasattr(data_source.query_runner, 'run_secure_query'):
        return False
    return ismethod(data_source.query_runner.run_secure_query)


def can_access(user, data_source):
    """Check user can access data source.

        Parameters:
        :user: user to access data_source
        :data_source: data source to be accessed.
        :return:
    """

    # check user is super admin.
    org = models.Organization.query.filter(models.Organization.id == user.org_id).one()
    for gid in user.group_ids:
        group = models.Group.get_by_id_and_org(gid, org)
        if "super_admin" in group.permissions:
            return True

    # check user can access the data source.
    for gid in data_source.groups:
        if gid in user.group_ids:
            return True

    return False


def varanus_render(template, context=None, **kwargs):
    str = mustache_render(template, context, **kwargs)
    renderer = pystache.Renderer()
    parsed = pystache.parse(str, (u'%(', u')s'))
    return renderer.render(parsed, context)


def has_parameter(query_text):
    from redash.utils.parameterized_query import _collect_query_parameters, _collect_key_names
    if len(_collect_query_parameters(query_text)) > 0:
        return True
    nodes = pystache.parse(query_text, (u'%(', u')s'))
    return len(_collect_key_names(nodes)) > 0


def get_tenant_id(headers):
    return headers.get('X-VARANAUS-PARAM-TENANT-ID', type=int)


CHROMELOGGER_ENABLED = parse_boolean(os.environ.get("VARANUS_REDASH_CHROMELOGGER_ENABLED", "false"))
DBOBJ_PREFIX=os.environ.get('VARANUS_REDASH_DATABASE_OBJECTPREFIX', '')
