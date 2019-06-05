from inspect import ismethod

version = '1.0.2'

def can_query_securely(data_source):
    if not hasattr(data_source.query_runner, 'run_secure_query'):
        return False
    return ismethod(data_source.query_runner.run_secure_query)
