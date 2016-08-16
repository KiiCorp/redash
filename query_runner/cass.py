import json
import sys
import logging

from redash.query_runner import *
from redash.utils import JSONEncoder

logger = logging.getLogger(__name__)

class Cassandra(BaseQueryRunner):
    @classmethod
    def configuration_schema(cls):
        return {
            'type': 'object',
            'properties': {
                'host': {
                    'type': 'string',
                },
                'port': {
                    'type': 'number',
                    'default': 9042,
                },
                'Keyspace': {
                    'type': 'string',
                    'title': 'Keyspace name'
                },
                'username': {
                    'type': 'string',
                    'title': 'Username'
                },
                'password': {
                    'type': 'string',
                    'title': 'Password'
                }
            },
            'required': ['Keyspace']
        }

    @classmethod
    def type(cls):
        return "Cassandra"

    @classmethod
    def enabled(cls):
        try:
            from cassandra.cluster import Cluster
        except ImportError:
            return False

        return True

    def _get_tables(self, schema):
        query = """
        select columnfamily_name from system.schema_columnfamilies where keyspace_name = '{}';
        """.format(self.configuration['Keyspace'])

        results = self.run_query(query)
        return results, error

    def run_query(self, query):
        from cassandra.cluster import Cluster
        connection = None
        try:
            if self.configuration.get('username', '') and self.configuration.get('password', ''):
                auth_provider = PlainTextAuthProvider(username='{}'.format(self.configuration.get('username', '')),
                                                      password='{}'.format(self.configuration.get('password', '')))
                connection = Cluster([self.configuration.get('host', '')], auth_provider=auth_provider)
            else:
                connection = Cluster([self.configuration.get('host', '')])

            session = connection.connect()
            logger.info("Cassandra running query: %s", query)
            result = session.execute(query)

            column_names = []
            columns = []
            for i in result.column_names:
                column_names.append(i)

            for column_name in column_names:

                columns.append({
                    'name': column_name,
                    'friendly_name': column_name,
                    'type': 'string'
                })
            rows = [dict(zip(column_names, row)) for row in result]

            data = {'columns': columns, 'rows': rows}
            json_data = json.dumps(data, cls=JSONEncoder)

            error = None

        except cassandra.cluster.Error, e:
            error = e.args[1]
        except KeyboardInterrupt:
            error = "Query cancelled by user."
        except Exception as e:
            raise sys.exc_info()[1], None, sys.exc_info()[2]

        return json_data, error

class ScyllaDB(Cassandra):
    @classmethod
    def type(cls):
        return "scylla"

    @classmethod
    def configuration_schema(cls):
        return {
           'type': 'object',
           'properties': {
               'host': {
                   'type': 'string',
               },
               'port': {
                   'type': 'number',
                   'default': 9042,
               },
               'Keyspace': {
                   'type': 'string',
                   'title': 'Keyspace name'
               },
               'username': {
                   'type': 'string',
                   'title': 'Username'
               },
               'password': {
                   'type': 'string',
                   'title': 'Password'
               }
           },
           'required': ['Keyspace']
       }

register(Cassandra)
register(ScyllaDB)
