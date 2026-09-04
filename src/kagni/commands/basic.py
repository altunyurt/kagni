from typing import List
import fnmatch
import re

from kagni.constants import Error, Errors, Response
from kagni.data import Data
from .common import KIND_STRING, expect_kind, kind_of
from .decorator import command_decorator

# redis-style 64-bit signed integer range for INCR/DECR
INT64_MIN = -(2 ** 63)
INT64_MAX = 2 ** 63 - 1

# non-negative or negative decimal integer, e.g. b"0", b"-42"
RE_NUMERIC = re.compile(rb"-?\d+\Z", re.ASCII)

# redis-compatible cap for a single string value (proto-max-bulk-len)
MAX_STRING_SIZE = 512 * 1024 * 1024

# parameters exposed through CONFIG GET (redis-benchmark probes these;
# real redis replies with a flat list of alternating name/value pairs)
CONFIG_VALUES = {
    b"maxmemory": b"0",
    b"maxmemory-policy": b"noeviction",
    b"save": b"",
    b"appendonly": b"no",
}


def _config_get(pattern: bytes) -> list:
    """CONFIG GET reply: every matching parameter as name/value pairs,
    or an empty array when nothing matches (redis behaviour)."""
    re_pattern = fnmatch.translate(pattern.decode("utf-8", "surrogateescape"))
    rgx = re.compile(re_pattern.encode("utf-8", "surrogateescape"))
    reply = []
    for name in sorted(CONFIG_VALUES):
        if rgx.match(name):
            reply.extend((name, CONFIG_VALUES[name]))
    return reply

__all__ = ["CommandSetMixin"]


class CommandSetMixin:
    @command_decorator(b"PING")
    def PING(self, message: bytes = None) -> (Response.PONG, bytes):
        return message if message is not None else Response.PONG

    @command_decorator(b"COMMAND")
    def COMMAND(self, *args) -> Response.OK:
        return Response.OK

    @command_decorator(b"CONFIG")
    def CONFIG(self, *args: bytes) -> list:
        """Minimal CONFIG: GET is enough for clients that probe the server
        (redis-benchmark fetches ``save`` and ``appendonly`` at startup and
        warns when the reply is missing).

        Values describe kagni honestly: no maxmemory limit, no classic
        snapshot "save" policy (the sqlite dump runs in a worker thread
        and is not fork-based), no appendonly file.
        """
        if not args:
            raise Errors.arity("config")
        subcommand = args[0].upper()
        if subcommand == b"GET":
            if len(args) != 2:
                raise Errors.arity("config|get")
            return _config_get(args[1])
        raise Error(
            "ERR",
            "Unknown CONFIG subcommand or wrong number of arguments for {}".format(
                subcommand.decode("ascii", "replace")
            ),
        )

    # ------------------------------------------------------------- helpers
    def _string(self, key):
        """Value of a string-typed key; None when missing/expired."""
        return expect_kind(self.data, key, KIND_STRING)

    # ------------------------------------------------------------------ core
    @command_decorator(b"SET")
    def SET(self, key: bytes, val: bytes) -> Response.OK:
        if len(val) > MAX_STRING_SIZE:
            raise Errors.STRING_OVERFLOW
        self.data[key] = val
        return Response.OK

    @command_decorator(b"GET")
    def GET(self, key: bytes) -> (bytes, Response.NIL):
        val = self._string(key)
        return Response.NIL if val is None else val

    @command_decorator(b"GETSET")
    def GETSET(self, key: bytes, val: bytes) -> (bytes, Response.NIL):
        retval = self._string(key)
        self.data[key] = val
        return Response.NIL if retval is None else retval

    @command_decorator(b"MGET")
    def MGET(self, *keys) -> list:
        out = []
        for key in keys:
            val = self._string(key)
            out.append(Response.NIL if val is None else val)
        return out

    @command_decorator(b"MSET")
    def MSET(self, *args: bytes) -> Response.OK:
        if len(args) < 2 or len(args) % 2:
            raise Errors.arity("mset")
        self.data.update(zip(args[::2], args[1::2]))
        return Response.OK

    @command_decorator(b"DEL")
    def DEL(self, *keys) -> int:
        return sum(self.data.remove(key) for key in keys)

    @command_decorator(b"EXPIRE")
    def EXPIRE(self, key: bytes, secs: int) -> int:
        return self.data.expire(key, secs)

    @command_decorator(b"PERSIST")
    def PERSIST(self, key: bytes) -> int:
        return self.data.persist(key)

    @command_decorator(b"TTL")
    def TTL(self, key: bytes) -> int:
        return self.data.ttl(key)

    @command_decorator(b"KEYS")
    def KEYS(self, pattern: bytes = None) -> List[bytes]:
        # surrogateescape keeps raw (non-utf8) patterns and keys working
        re_pattern = fnmatch.translate(
            (pattern if pattern is not None else b"*").decode(
                "utf-8", "surrogateescape"
            )
        )
        rgx = re.compile(re_pattern.encode("utf-8", "surrogateescape"))
        return [key for key in self.data if rgx.match(key)]

    # ----------------------------------------------------------- counters
    def _bump(self, key, by):
        """Shared INCR/INCRBY/DECR/DECRBY implementation."""
        val = self.data.get(key)
        if val is None:
            current = 0
        elif kind_of(val) != KIND_STRING:
            raise Errors.WRONGTYPE
        elif not RE_NUMERIC.match(val):
            raise Errors.NOT_INT
        else:
            current = int(val, 10)

        result = current + by
        if result < INT64_MIN or result > INT64_MAX:
            raise Errors.OVERFLOW
        self.data[key] = f"{result}".encode()
        return result

    @command_decorator(b"INCRBY")
    def INCRBY(self, key: bytes, i: int) -> int:
        return self._bump(key, i)

    @command_decorator(b"INCR")
    def INCR(self, key: bytes) -> int:
        return self._bump(key, 1)

    @command_decorator(b"DECRBY")
    def DECRBY(self, key: bytes, i: int) -> int:
        return self._bump(key, -i)

    @command_decorator(b"DECR")
    def DECR(self, key: bytes) -> int:
        return self._bump(key, -1)

    # -------------------------------------------------------------- ranges
    @command_decorator(b"GETRANGE")
    def GETRANGE(self, key: bytes, start: int, end: int) -> bytes:
        val = self._string(key)
        if val is None:
            return b""
        # redis-style inclusive end, supporting negative offsets: convert
        # to a python slice end (exclusive, relative to the length)
        stop = end + 1 if end >= 0 else len(val) + end + 1
        return val[start:stop]

    @command_decorator(b"SETRANGE")
    def SETRANGE(self, key: bytes, offset: int, value: bytes) -> int:
        if offset < 0:
            raise Errors.RANGE_OFFSET
        val = self._string(key)
        if val is None:
            val = b""
        if offset + len(value) > MAX_STRING_SIZE:
            raise Errors.STRING_OVERFLOW

        if offset > len(val):
            val = val.ljust(offset, b"\x00") + value
        else:
            val = val[:offset] + value + val[offset + len(value):]
        self.data[key] = val
        return len(val)

    # ---------------------------------------------------------------- misc
    @command_decorator(b"FLUSHDB")
    def FLUSHDB(self):
        self.data = Data()
        if self.persistence is not None:
            self.persistence.flush()
        return Response.OK

    @command_decorator(b"FLUSHALL")
    def FLUSHALL(self):
        self.data = Data()
        if self.persistence is not None:
            self.persistence.flush()
        return Response.OK

    @command_decorator(b"APPEND")
    def APPEND(self, key: bytes, val: bytes) -> int:
        current = self._string(key)
        value = (current if current is not None else b"") + val
        if len(value) > MAX_STRING_SIZE:
            raise Errors.STRING_OVERFLOW
        self.data[key] = value
        return len(value)

    @command_decorator(b"STRLEN")
    def STRLEN(self, key: bytes) -> int:
        val = self._string(key)
        return len(val) if val is not None else 0
