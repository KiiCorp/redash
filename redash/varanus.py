from inspect import ismethod
from redash.utils import mustache_render

import pystache

version = '1.0.2'

def can_query_securely(data_source):
    if not hasattr(data_source.query_runner, 'run_secure_query'):
        return False
    return ismethod(data_source.query_runner.run_secure_query)

def varanus_render(template, context=None, **kwargs):
    str = mustache_render(template, context, **kwargs)
    renderer = pystache.Renderer()
    parsed = pystache.parse(str, (u'%(', u')s'))
    return renderer.render(parsed, context)
