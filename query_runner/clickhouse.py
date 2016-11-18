import json
import logging
from redash.query_runner import *
from redash.utils import JSONEncoder
import pprint
logger = logging.getLogger(__name__)

pp = pprint.PrettyPrinter()

try:
    import requests
    enabled = True
except ImportError as e:
    logger.info(str(e))
    enabled = False


class ClickHouse(BaseSQLQueryRunner):
    noop_query = "SELECT 1"

    @classmethod
    def configuration_schema(cls):
        return {
            "type": "object",
            "properties": {
                "user": {
                    "type": "string",
                    "default": "default"
                },
                "password": {
                    "type": "string"
                },
                "host": {
                    "type": "string",
                    "default": "127.0.0.1"
                },
                "port": {
                    "type": "number",
                    "default": 8123
                },
                "dbname": {
                    "type": "string",
                    "title": "Database Name"
                }
            },
            "required": ["dbname"],
            "secret": ["password"]
        }

    @classmethod
    def type(cls):
        return "clickhouse"

    def __init__(self, configuration):
        super(ClickHouse, self).__init__(configuration)

    def _get_tables(self, schema):
        query = "SELECT database, table, name FROM system.columns WHERE database NOT IN ('system')"

        results, error = self.run_query(query, None)

        if error is not None:
            raise Exception("Failed getting schema.")

        results = json.loads(results)

        for row in results['rows']:
            table_name = '{}.{}'.format(row['database'], row['table'])

            if table_name not in schema:
                schema[table_name] = {'name': table_name, 'columns': []}

            schema[table_name]['columns'].append(row['name'])

        return schema.values()

    def _send_query(self, data, stream=False):
        url = 'http://{host}:{port}'.format(host=self.configuration['host'], port=self.configuration['port'])
        r = requests.post(url, data=data, stream=stream, params={
            'user': self.configuration['user'], 'password':  self.configuration['password'],
            'database': self.configuration['dbname']
        })
        if r.status_code != 200:
            raise Exception(r.text)
        return r.json()

    @staticmethod
    def _define_column_type(column):
        c = column.lower()
        if 'int' in c:
            return 'integer'
        elif 'float' in c:
            return 'float'
        else:
            return 'string'

    def _clickhouse_query(self, query):
        query += ' FORMAT JSON'
        result = self._send_query(query)
        columns = [{'name': r['name'], 'friendly_name': r['name'],
                    'type': self._define_column_type(r['type'])} for r in result['meta']]
        return {'columns': columns, 'rows': result['data']}

    def run_query(self, query, user):
        logger.info("Clickhouse is about to execute query: %s", query)
        if query == "":
            json_data = None
            error = "Query is empty"
            return json_data, error
        try:
            q = self._clickhouse_query(query)
            data = json.dumps(q, cls=JSONEncoder)
            error = None
        except Exception as exc:
            data = None
            error = str(exc)
        return data, error

register(ClickHouse)
