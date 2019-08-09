from typing import List
import fnmatch
import re

from kagni.constants import Errors, Response
from kagni.data import Data


RE_NUMERIC = re.compile(b"^\d+$", re.ASCII)

__all__ = ["CommandSetMixin"]


class CommandSetMixin:
    def PING(self) -> Response.PONG:
        return Response.PONG

    def COMMAND(self, *args) -> Response.OK:
        return Response.OK

    def SET(self, key: bytes, val: bytes) -> Response.OK:
        self.data[key] = val
        return Response.OK

    def GET(self, key: bytes) -> (bytes, Response.NIL):
        return self.data.get(key, Response.NIL)

    def GETSET(self, key: bytes, val: bytes) -> (bytes, Response.NIL):
        retval = self.data.get(key, Response.NIL)
        self.data[key] = val
        return retval

    def MGET(self, *keys) -> list:
        return [self.data.get(key, Response.NIL) for key in keys]

    def MSET(self, *args: bytes) -> Response.OK:
        chunks = [args[i : i + 2] for i in range(0, len(args), 2)]
        self.data.update(dict(chunks))
        return Response.OK

    def DEL(self, *keys) -> int:
        return sum([self.data.remove(key) for key in keys])

    def EXPIRE(self, key: bytes, secs: int) -> int:
        secs = int(secs)
        return self.data.expire(key, secs)

    def PERSIST(self, key: bytes, secs: int) -> int:
        secs = int(secs)
        return self.data.persist(key)

    def TTL(self, key: bytes) -> int:
        return self.data.ttl(key)

    def KEYS(self, pattern: bytes = None) -> List[bytes]:
        re_pattern = fnmatch.translate(pattern.decode() if pattern else "*")
        rgx = re.compile(re_pattern.encode())
        return [key for key in self.data if rgx.match(key)]

    def INCRBY(self, key: bytes, i: int) -> int:
        val = b"0"
        if key in self.data:
            val = self.data[key]
            if not RE_NUMERIC.match(val):
                raise Errors.WRONGTYPE

        _val = int(val, 10) + int(i)
        self.data[key] = f"{ _val }".encode()
        return _val

    def INCR(self, key: bytes) -> int:
        val = b"0"
        if key in self.data:
            val = self.data[key]
            if not RE_NUMERIC.match(val):
                raise Errors.WRONGTYPE

        _val = int(val, 10) + 1
        self.data[key] = f"{ _val }".encode()
        return _val

    def DECRBY(self, key: bytes, i: int) -> int:
        val = b"0"
        if key in self.data:
            val = self.data[key]
            if not RE_NUMERIC.match(val):
                raise Errors.WRONGTYPE

        _val = int(val, 10) - int(i)
        self.data[key] = f"{ _val }".encode()
        return _val

    def DECR(self, key: bytes) -> int:
        val = b"0"
        if key in self.data:
            val = self.data[key]
            if not RE_NUMERIC.match(val):
                raise Errors.WRONGTYPE

        _val = int(val, 10) - 1
        self.data[key] = f"{ _val }".encode()
        return _val

    def GETRANGE(self, key: bytes, start: int, end: int) -> bytes:
        val = self.data.get(key, b"")
        return val[int(start) : int(end) + 1]

    def SETRANGE(self, key: bytes, offset: int, value: bytes) -> bytes:
        val = self.data.get(key, b"")

        offset = int(offset)
        if offset > len(val):
            val = val.ljust(offset, b"\x00") + value
        else:
            val = val[:offset] + value + val[offset + len(value) :]
        self.data[key] = val
        return len(val)

    def FLUSHDB(self):
        self.data = Data()
        # TODO: wipe the sqlite3 backend
        return Response.OK

    def FLUSHALL(self):
        self.data = Data()
        # TODO: wipe the sqlite3 backend
        return Response.OK

    def APPEND(self, key: bytes, val: bytes) -> int:
        value = self.data.get(key, b"") + val
        self.data[key] = value
        return len(value)

    def STRLEN(self, key: bytes) -> int:
        return len(self.data.get(key, b""))
