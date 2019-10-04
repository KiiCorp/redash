import os
from inspect import ismethod
from redash.utils import mustache_render
from redash.settings.helpers import parse_boolean

import pystache

version = '1.1.0'


def can_query_securely(data_source):
    if not hasattr(data_source.query_runner, 'run_secure_query'):
        return False
    return ismethod(data_source.query_runner.run_secure_query)


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


CHROMELOGGER_ENABLED = parse_boolean(os.environ.get("VARANUS_REDASH_CHROMELOGGER_ENABLED", "false"))
DBOBJ_PREFIX=os.environ.get('VARANUS_REDASH_DATABASE_OBJECTPREFIX', '')
