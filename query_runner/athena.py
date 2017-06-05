import logging
import json

from redash.utils import JSONEncoder
from redash.query_runner import *


logger = logging.getLogger(__name__)


try:
    import pyathena
    enabled = True
except ImportError:
    enabled = False


_TYPE_MAPPINGS = {
    'boolean': TYPE_BOOLEAN,
    'tinyint': TYPE_INTEGER,
    'smallint': TYPE_INTEGER,
    'integer': TYPE_INTEGER,
    'bigint': TYPE_INTEGER,
    'double': TYPE_FLOAT,
    'varchar': TYPE_STRING,
    'timestamp': TYPE_DATETIME,
    'date': TYPE_DATE,
    'varbinary': TYPE_STRING,
    'array': TYPE_STRING,
    'map': TYPE_STRING,
    'row': TYPE_STRING,
    'decimal': TYPE_FLOAT,
}


class Athena(BaseQueryRunner):
    noop_query = 'SELECT 1'

    @classmethod
    def name(cls):
        return "Amazon Athena"

    @classmethod
    def configuration_schema(cls):
        return {
            'type': 'object',
            'properties': {
                'region': {
                    'type': 'string',
                    'title': 'AWS Region'
                },
                'aws_access_key': {
                    'type': 'string',
                    'title': 'AWS Access Key'
                },
                'aws_secret_key': {
                    'type': 'string',
                    'title': 'AWS Secret Key'
                },
                's3_staging_dir': {
                    'type': 'string',
                    'title': 'S3 Staging Path'
                },
                'schema': {
                    'type': 'string',
                    'title': 'Schema Name',
                    'default': 'default'
                },
                'encryption_option': {
                    'type': 'string',
                    'title': 'Encryption Option',
                },
                'kms_key': {
                    'type': 'string',
                    'title': 'KMS Key',
                },
            },
            'required': ['region', 's3_staging_dir']
        }

    @classmethod
    def enabled(cls):
        return enabled

    @classmethod
    def type(cls):
        return "athena"

    def __init__(self, configuration):
        super(Athena, self).__init__(configuration)

    def get_schema(self, get_stats=False):
        schema = {}
        query = """
        SELECT table_schema, table_name, column_name
        FROM information_schema.columns
        WHERE table_schema NOT IN ('information_schema')
        """

        results, error = self.run_query(query, None)
        if error is not None:
            raise Exception("Failed getting schema.")

        results = json.loads(results)
        for row in results['rows']:
            table_name = '{0}.{1}'.format(row['table_schema'], row['table_name'])
            if table_name not in schema:
                schema[table_name] = {'name': table_name, 'columns': []}
            schema[table_name]['columns'].append(row['column_name'])

        return schema.values()

    def run_query(self, query, user):
        cursor = pyathena.connect(
            s3_staging_dir=self.configuration['s3_staging_dir'],
            region_name=self.configuration['region_name'],
            aws_access_key_id=self.configuration.get('aws_access_key', None),
            aws_secret_access_key=self.configuration.get('aws_secret_key', None),
            schema_name=self.configuration.get('schema', 'default'),
            encryption_option=self.configuration.get('encryption_option', None),
            kms_key=self.configuration.get('kms_key', None)).cursor()

        try:
            cursor.execute(query)
            column_tuples = [(i[0], _TYPE_MAPPINGS.get(i[1], None)) for i in cursor.description]
            columns = self.fetch_columns(column_tuples)
            rows = [dict(zip(([c['name'] for c in columns]), r)) for i, r in enumerate(cursor.fetchall())]
            data = {'columns': columns, 'rows': rows}
            json_data = json.dumps(data, cls=JSONEncoder)
            error = None
        except KeyboardInterrupt:
            cursor.cancel()
            error = "Query cancelled by user."
            json_data = None
        except Exception, ex:
            cursor.cancel()
            error = ex.message
            json_data = None

        return json_data, error


register(Athena)
