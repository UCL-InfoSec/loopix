# format 3
from os import urandom
from collections import namedtuple
from binascii import hexlify
from copy import copy
import math

from hashlib import sha512, sha1
import hmac

import msgpack

from petlib.ec import EcGroup
from petlib.ec import EcPt
from petlib.bn import Bn
from petlib.cipher import Cipher
import base64
import petlib.pack
import binascii

import time

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
    'TIME_PULL'])

Params.__new__.__defaults__ = (None,) * len(Params._fields)
