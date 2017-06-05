from collections import namedtuple

Keys = namedtuple('Keys', ['b', 'iv', 'kmac', 'kenc'])
Mix = namedtuple('Mix', ['name', 'port', 'host', 'pubk', 'group'])
Provider = namedtuple('Provider', ['name', 'port', 'host', 'pubk'])
User = namedtuple('User', ['name', 'port', 'host', 'pubk', 'provider'])

Params = namedtuple('Params',
    ['EXP_PARAMS_LOOPS',
    'EXP_PARAMS_DROP',
    'EXP_PARAMS_PAYLOAD',
    'EXP_PARAMS_DELAY',
    'DATABASE_NAME',
    'TIME_PULL',
    'MAX_DELAY_TIME',
    'NOISE_LENGTH',
    'MAX_RETRIEVE'])

Params.__new__.__defaults__ = (None,) * len(Params._fields)
