import logging
import inspect
import re
from collections import deque
from functools import partial
from functools import reduce
from functools import wraps
from math import ceil
from pyroaring import BitMap
from typing import List
import fnmatch

from .constants import Errors
from .constants import OK
from .constants import NIL
from .constants import PONG
from .resp import protocolBuilder
from .data import Data

# from .data import self.data

log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)
log.addHandler(logging.StreamHandler())


__all__ = ["Commands"]

CASTERS = {
    "bytes_to_int": lambda arg: int(arg, base=10),
    "bytes_to_str": lambda arg: arg.decode(),
}
RE_NUMERIC = re.compile(b"^\d+$", re.ASCII)


# https://github.com/chekart/rediserver


# register command to commands repo
def command_decorator(name):
    def wrapper(f):

        f_specs = inspect.getfullargspec(f)
        f_args = f_specs.args[1:]  # exclude self
        f_varargs = f_specs.varargs
        f_annotations = f_specs.annotations

        @wraps(f)
        def inner(instance, *c_args):  # calling args
            args_list = []

            if f_args:

                for arg_name, arg in zip(f_args, c_args):
                    _type = f_annotations.get(arg_name)
                    if _type and _type != bytes:
                        arg = CASTERS[f"bytes_to_{_type.__name__}"](arg)

                    args_list.append(arg)

            if f_varargs:
                # push the rest of varargs in
                args_list.extend(c_args[len(f_args) :])

            retval = f(instance, *args_list)
            return protocolBuilder(retval)

        return inner

    return wrapper


class Commands:
    def __init__(self, data=None):
        self.data = data if data is not None else {}

    @command_decorator({"name": b"PING"})
    def PING(self) -> PONG:
        return PONG

    @command_decorator(b"COMMAND")
    def COMMAND(self, *args) -> OK:
        return OK

    @command_decorator(b"SET")
    def SET(self, key: bytes, val: bytes) -> OK:
        self.data[key] = val
        return OK

    @command_decorator(b"GET")
    def GET(self, key: bytes) -> (bytes, NIL):
        return self.data.get(key, NIL)

    @command_decorator(b"GETSET")
    def GETSET(self, key: bytes, val: bytes) -> (bytes, NIL):
        retval = self.data.get(key, NIL)
        self.data[key] = val
        return retval

    @command_decorator(b"MGET")
    def MGET(self, *keys) -> list:
        return [self.data.get(key, NIL) for key in keys]

    @command_decorator(b"MSET")
    def MSET(self, *args: bytes) -> OK:
        chunks = [args[i : i + 2] for i in range(0, len(args), 2)]
        self.data.update(dict(chunks))
        return OK

    @command_decorator(b"DEL")
    def DEL(self, *keys) -> int:
        return sum([self.data.remove(key) for key in keys])

    @command_decorator(b"EXPIRE")
    def EXPIRE(self, key: bytes, secs: int) -> int:
        return self.data.expire(key, secs)

    @command_decorator(b"TTL")
    def TTL(self, key: bytes) -> int:
        return self.data.ttl(key)

    @command_decorator(b"KEYS")
    def KEYS(self, pattern: bytes = None) -> List[bytes]:
        re_pattern = fnmatch.translate(pattern.decode() if pattern else "*")
        rgx = re.compile(re_pattern.encode())
        return [key for key in self.data if rgx.match(key)]

    @command_decorator(b"INCRBY")
    def INCRBY(self, key: bytes, i: int) -> int:
        val = b"0"
        if key in self.data:
            val = self.data[key]
            if not RE_NUMERIC.match(val):
                raise Errors.WRONGTYPE

        _val = int(val, 10) + i
        self.data[key] = f"{ _val }".encode()
        return _val

    @command_decorator(b"INCR")
    def INCR(self, key: bytes) -> int:
        val = b"0"
        if key in self.data:
            val = self.data[key]
            if not RE_NUMERIC.match(val):
                raise Errors.WRONGTYPE

        _val = int(val, 10) + 1
        self.data[key] = f"{ _val }".encode()
        return _val

    @command_decorator(b"GETRANGE")
    def GETRANGE(self, key: bytes, start: int, end: int) -> List[bytes]:
        val = self.data.get(key, b"")
        return val[start : end + 1]

    ###############
    ##BIT ops
    @command_decorator(b"SETBIT")
    def SETBIT(self, key: bytes, bit: int, val: int) -> int:

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
        return ex_val

    @command_decorator(b"GETBIT")
    def GETBIT(self, key: bytes, bit: int) -> int:
        if key not in self.data:
            return 0

        return 1 if bit in self.data[key] else 0

    @command_decorator(b"BITOP")
    def BITOP(self, op: bytes, dest_name: bytes, *keys) -> int:
        op = op.upper()
        maps = [self.data.get(key, BitMap()) for key in keys]

        self.data[dest_name] = {
            b"AND": partial(reduce, lambda x, y: x & y, maps[1:], maps[0]),
            b"OR": partial(reduce, lambda x, y: x | y, maps[1:], maps[0]),
            b"XOR": partial(reduce, lambda x, y: x ^ y, maps[1:], maps[0]),
            b"NOT": lambda: maps[0].flip(0, maps[0].max()),
        }[op]()

        # redis protocol compatibility. should return the longest string's length
        # but roaring bitmaps only care about 1's. so we'll have to make it up
        max_len = max([self.data.get(i).max() for i in [dest_name, *keys]])
        return ceil(max_len / 8)

    @command_decorator(b"BITCOUNT")
    def BITCOUNT(self, key: bytes) -> int:
        if key not in self.data:
            return 0
        return len(self.data[key])

    @command_decorator(b"BITPOS")
    def BITPOS(self, key: bytes, bit: bytes) -> int:
        retval = -1

        if key not in self.data:
            return retval

        bmap = self.data[key]

        # no bits set yet, so only meaningful for checking 0 bit
        if not len(bmap):
            if bit == b"1":
                retval = -1
            else:
                retval = 0

        else:
            if bit == b"1":
                retval = bmap.min()
            else:
                # xor the bitmap with an all 1s map of same length.
                # min value of the result map is where it's 0 for the original map
                retval = (bmap ^ BitMap(range(bmap.max() + 1))).min()
        return retval

    @command_decorator(b"FLUSHDB")
    def FLUSHDB(self):
        self.data = Data()
        # TODO: wipe the sqlite3 backend
        return OK

    @command_decorator(b"FLUSHALL")
    def FLUSHALL(self):
        self.data = Data()
        # TODO: wipe the sqlite3 backend
        return OK

    @command_decorator(b"HSET")
    def HSET(self, key: bytes, field: bytes, val: bytes) -> int:
        retval = 0  # field is new

        if key not in self.data:
            self.data[key] = {}
            retval = 1
        elif field not in self.data[key]:
            retval = 1

        self.data[key][field] = val
        return retval

    @command_decorator(b"HGET")
    def HGET(self, key: bytes, field: bytes) -> (bytes, NIL):
        data = self.data
        if key not in data:
            return NIL

        if field not in data[key]:
            return NIL

        return data[key][field]

    @command_decorator(b"HEXISTS")
    def HEXISTS(self, key: bytes, field: bytes) -> int:
        data = self.data
        if key not in data:
            return 0

        if field not in data[key]:
            return 0

        return 1

    @command_decorator(b"HDEL")
    def HDEL(self, key: bytes, *fields: List[bytes]) -> int:
        if key not in self.data:
            return 0

        data = self.data[key]
        retval = 0
        for field in fields:
            if field not in data:
                continue
            del data[field]
            retval += 1
        return retval

    @command_decorator(b"HGETALL")
    def HGETALL(self, key: bytes) -> List[bytes]:
        if key not in self.data:
            return []
        data = self.data[key]
        return [b for a in data.items() for b in a]
