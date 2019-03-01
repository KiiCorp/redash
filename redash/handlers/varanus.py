from redash import __version__, varanus
from redash.handlers import routes
from redash.handlers.base import json_response

@routes.route('/api/varanus/version', methods=['GET'])
def varanus_version():
    return json_response({
        'version': "%s-%s" % (varanus.version, __version__)
    })
