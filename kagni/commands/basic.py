from typing import List
import fnmatch
import re

from kagni.constants import Errors, OK, NIL, PONG
from kagni.data import Data
from .decorator import command_decorator


RE_NUMERIC = re.compile(b"^\d+$", re.ASCII)

__all__ = ["CommandSetMixin"]


class CommandSetMixin:
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
