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
import inspect

log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)
log.addHandler(logging.StreamHandler())


__all__ = ["COMMANDS"]

CASTERS = {"bytes_to_int": lambda arg: int(arg), "bytes_to_str": lambda arg: arg.decode()}


DATA = {}
EXPIRES = {}
COMMANDS = {}

# https://github.com/chekart/rediserver
SYM_CRLF = b"\r\n"
OK = object()
QUEUED = object()
PONG = object()
NIL = None


class Error(Exception):
    def __init__(self, class_, msg=""):
        self.class_ = class_
        self.message = msg


class Errors:
    INVALID_CURSOR = Error("ERR", "invalid cursor")
    NOT_INT = Error("ERR", "value is not an integer or out of range")
    WRONGTYPE = Error(
        "WRONGTYPE", "Operation against a key holding the wrong kind of value"
    )


# https://github.com/chekart/rediserver
def _resp_dumps(value):
    if value is OK:
        return [b"+OK"]

    if value is NIL:
        return [b"$-1"]

    if value is QUEUED:
        return [b"+QUEUED"]

    if value is PONG:
        return [b"+PONG"]

    if value is QUEUED:
        return [b"+QUEUED"]

    if isinstance(value, int):
        return [b":" + str(value).encode()]

    if isinstance(value, str):
        value = value.encode()

    if isinstance(value, bytes):
        return [b"$" + str(len(value)).encode(), value]

    if isinstance(value, Error):
        return [b"-" + str(value.class_).encode() + b" " + str(value.message).encode()]

    if isinstance(value, (list, tuple)):
        result = [b"*" + str(len(value)).encode()]
        for item in value:
            result.extend(_resp_dumps(item))
        return result

    raise NotImplementedError()


def dump_response(value):
    response = _resp_dumps(value)
    response = SYM_CRLF.join(response) + SYM_CRLF
    return response


# register command to commands repo
def register_command(name):
    def wrapper(f):

        f_specs = inspect.getfullargspec(f)
        f_args = f_specs.args
        f_varargs = f_specs.varargs
        f_annotations = f_specs.annotations

        @wraps(f)
        def inner(*c_args):  # calling args
            args_list = []

            if f_args:
                for name, arg in zip(f_args, c_args):
                    _type = f_annotations.get(name)
                    if _type and _type != bytes:
                        arg = CASTERS[f"bytes_to_{_type.__name__}"](arg)

                    args_list.append(arg)

            if f_varargs:
                # push the rest of varargs in
                args_list.extend(c_args[len(f_args) :])


            retval = f(*args_list)
            return dump_response(retval)

        COMMANDS[name] = inner
        return inner

    return wrapper


@register_command(b"PING")
def _ping():
    return PONG


@register_command(b"COMMAND")
def _command(*args):
    return OK


@register_command(b"SET")
def _set(key: bytes, val: bytes):
    DATA[key] = val
    return OK


@register_command(b"GET")
def _get(key: bytes):
    return DATA.get(key, NIL)


@register_command(b"MGET")
def _mget(*keys):
    return [_get(key, NIL) for key in keys]


@register_command(b"MSET")
def _mset(*args):
    chunks = [args[i : i + 2] for i in range(0, len(args), 2)]
    for (key, val) in chunks:
        _set(key, val)
    return OK


@register_command(b"DEL")
def _del_(*keys):
    cnt = 0
    for key in keys:
        if key in DATA:
            del DATA[key]
            cnt += 1
    return cnt


@register_command(b"EXPIRE")
def _expire(key: bytes, secs: int):
    if key not in DATA:
        return 0

    EXPIRES[key] = monotonic_ns_time() + secs * (10 ** 9)
    return 1


@register_command(b"TTL")
def ttl(key: bytes):
    if key not in DATA:
        return -2

    if key not in EXPIRES:
        return -1

    expires_at = EXPIRES.get(key)
    ttl = ceil((expires_at - monotonic_ns_time()) / (10 ** 9))
    return ttl if ttl >= 0 else -2


@register_command(b"KEYS")
def _keys(pattern):
    return [k for k in DATA]


@register_command(b"INCRBY")
def _incrby(key: bytes, i: int):
    val = DATA.get(key, 0)
    val += i
    DATA[key] = val
    return val


@register_command(b"INCR")
def _incr(key: bytes):
    return _incrby(key, 1)


@register_command(b"GETRANGE")
def _getrange(key: bytes, start: int, end: int):
    val = DATA.get(key, "")
    return val[start:end]


###############
## BIT ops
@register_command(b"SETBIT")
def _setbit(key: bytes, bit: int, val: int):

    ex_val = 0
    bmap = DATA.get(key, BitMap())

    if key not in DATA:
        DATA[key] = bmap
    else:
        ex_val = 1 if bit in bmap else 0

    if val:
        bmap.add(bit)
    elif ex_val:
        bmap.remove(bit)

    return ex_val


@register_command(b"GETBIT")
def _getbit(key: bytes, bit: int):
    if key not in DATA:
        return b":0\r\n"

    return 1 if int(bit) in DATA[key] else 0


@register_command(b"BITOP")
def _bitop(op: bytes, dest_name: bytes, *keys):
    op = op.lower()
    maps = [DATA.get(key, BitMap()) for key in keys]

    DATA[dest_name] = {
        b"and": partial(reduce, lambda x, y: x & y, maps[1:], maps[0]),
        b"or": partial(reduce, lambda x, y: x | y, maps[1:], maps[0]),
        b"xor": partial(reduce, lambda x, y: x ^ y, maps[1:], maps[0]),
        b"not": lambda: maps[0].flip(0, maps[0].max()),
    }[op]()

    return len(DATA[dest_name])


@register_command(b"BITCOUNT")
def _bitcount(key: bytes):
    if key not in DATA:
        return 0
    return len(DATA[key])


@register_command(b"BITPOS")
def _bitpos(key: bytes, bit: bytes):
    retval = -1

    if key not in DATA:
        return retval

    bmap = DATA[key]

    if not len(bmap):
        if bit == b"1":
            retval = -1
        else:
            retval = 0

    else:
        if bit == b"1":
            retval = bmap.min()
        else:
            retval = (bmap ^ BitMap(range(bmap.max() + 1))).min()
    return retval
