from collections import defaultdict
from collections import deque
from functools import lru_cache
from functools import partial
from functools import reduce
from functools import wraps
from math import ceil
from pyroaring import BitMap
from time import monotonic_ns as monotonic_ns_time
from types import GeneratorType
import logging

log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)
log.addHandler(logging.StreamHandler())


NULL = b"$-1\r\n"


class Wrapper:
    def __init__(self, *args):
        self.casters = {"bytes_to_int": lambda arg: int(arg), "bytes_to_str": lambda arg: arg.decode()}

    def __call__(self, f):
        @wraps(f)
        def inner(*args, **kwargs):
            args_list = []
            for name, arg in zip(f.__code__.co_varnames, args):

                _type = f.__annotations__.get(name)

                if _type and _type != bytes:
                    arg = self.casters[f"bytes_to_{_type.__name__}"](arg)

                args_list.append(arg)
            return f(*args_list, **kwargs)

        return inner


class Command:
    def __init__(self):

        self.data = {}
        self.expires = {}

        self.commands = {
            b"GET": self.get,
            b"SET": self.set_,
            b"PING": self.ping,
            b"EXPIRE": self.expire,
            b"TTL": self.ttl,
            b"MSET": self.mset,
            b"MGET": self.mget,
            b"COMMAND": self.command,
            b"DEL": self.del_,
            b"KEYS": self.keys,
            b"SETBIT": self.setbit,
            b"BITOP": self.bitop,
            b"GETBIT": self.getbit,
        }

    def command(self, *args):
        return b"+OK\r\n"

    def set_(self, key: bytes, val: bytes):
        self.data[key] = val

        return b"+OK\r\n"

    def mset(self, *args):
        chunks = [args[i : i + 2] for i in range(0, len(args), 2)]
        for (key, val) in chunks:
            self.set_(key, val)
        return b"+OK\r\n"

    def get(self, key):
        val = self.data.get(key)
        if not val:
            return NULL

        return b"+%s\r\n" % val

    def mget(self, *keys):
        arr = [self.get(key) for key in keys]
        len_ = f"{len(arr)}".encode()
        return b"*%s\r\n%s" % (len_, b"".join(arr))

    def del_(self, *keys):
        cnt = 0
        for key in keys:
            if key in self.data:
                del self.data[key]
                cnt += 1
        return cnt

    @Wrapper()
    def expire(self, key: bytes, secs: int):
        if key not in self.data:
            return b":0\r\n"

        self.expires[key] = monotonic_ns_time() + secs * (10 ** 9)
        return b":1\r\n"

    def ttl(self, key):
        if key not in self.data:
            return b":-2\r\n"

        if key not in self.expires:
            return b":-1\r\n"

        expires_at = self.expires.get(key)
        ttl = ceil((expires_at - monotonic_ns_time()) / (10 ** 9))
        return (":%s\r\n" % ttl).encode() if ttl >= 0 else b":-2\r\n"

    def keys(self, pattern):
        filter(self.data.keys())

    def ping(self):
        return b"+PONG\r\n"

    @Wrapper()
    def setbit(self, key: bytes, bit: int, val: int):

        ex_val = 0
        bmap = self.data.get(key, BitMap())

        if key not in self.data:
            self.data[key] = bmap
        else:
            ex_val = 1 if bit in bmap else 0

        if val:
            bmap.add(bit)
        elif ex_val:
            bmap.remove(bit)
        return (":%s\r\n" % ex_val).encode()

    @Wrapper()
    def getbit(self, key: bytes, bit: int):
        if key not in self.data:
            return b":0\r\n"

        retval = 1 if int(bit) in self.data[key] else 0
        return f":{retval}\r\n".encode()

    @Wrapper()
    def bitop(self, op: bytes, dest_name: bytes, *keys):
        op = op.lower()
        maps = [self.data.get(key, BitMap()) for key in keys]

        self.data[dest_name] = {
            b"and": partial(reduce, lambda x, y: x & y, maps[1:], maps[0]),
            b"or": partial(reduce, lambda x, y: x | y, maps[1:], maps[0]),
            b"xor": partial(reduce, lambda x, y: x ^ y, maps[1:], maps[0]),
            b"not": lambda: maps[0].flip(0, maps[0].max()),
        }[op]()

        return f":{len(self.data[dest_name])}\r\n".encode()
