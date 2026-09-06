from typing import List

from kagni.constants import Errors, Response
from .common import (
    INT64_MAX,
    INT64_MIN,
    KIND_HASH,
    RE_NUMERIC,
    compile_glob,
    expect_kind,
    parse_scan_cursor,
    parse_scan_options,
)
from .decorator import command_decorator

__all__ = ["CommandSetMixin"]


class CommandSetMixin:

    def _hash(self, key):
        """Hash stored under *key*; None when missing/expired."""
        return expect_kind(self.data, key, KIND_HASH)

    @command_decorator(b"HSET")
    def HSET(self, key: bytes, *field_values: bytes) -> int:
        """HSET key field value [field value ...] (variadic since redis
        4.0); replies with the number of fields that were newly added."""
        if len(field_values) < 2 or len(field_values) % 2:
            raise Errors.arity("hset")

        cur = self._hash(key)
        if cur is None:
            cur = {}
            self.data[key] = cur
        new_fields = 0
        for i in range(0, len(field_values), 2):
            field, value = field_values[i], field_values[i + 1]
            if field not in cur:
                new_fields += 1
            cur[field] = value
        return new_fields

    @command_decorator(b"HGET")
    def HGET(self, key: bytes, field: bytes) -> (bytes, Response.NIL):
        cur = self._hash(key)
        if cur is None or field not in cur:
            return Response.NIL
        return cur[field]

    @command_decorator(b"HMGET")
    def HMGET(self, key: bytes, *fields: bytes) -> list:
        """HMGET key field [field ...]: one reply slot per requested
        field, nil for missing fields and for a missing key alike."""
        if not fields:
            raise Errors.arity("hmget")
        cur = self._hash(key)
        if cur is None:
            return [Response.NIL] * len(fields)
        return [cur.get(field, Response.NIL) for field in fields]

    @command_decorator(b"HEXISTS")
    def HEXISTS(self, key: bytes, field: bytes) -> int:
        cur = self._hash(key)
        if cur is None or field not in cur:
            return 0
        return 1

    @command_decorator(b"HDEL")
    def HDEL(self, key: bytes, *fields: List[bytes]) -> int:
        if not fields:
            raise Errors.arity("hdel")
        cur = self._hash(key)
        if cur is None:
            return 0

        removed = 0
        for field in fields:
            if field in cur:
                del cur[field]
                removed += 1
        if not cur:
            # redis: the key disappears with its last field
            self.data.remove(key)
        return removed

    @command_decorator(b"HLEN")
    def HLEN(self, key: bytes) -> int:
        cur = self._hash(key)
        return 0 if cur is None else len(cur)

    @command_decorator(b"HKEYS")
    def HKEYS(self, key: bytes) -> List[bytes]:
        cur = self._hash(key)
        return [] if cur is None else list(cur)

    @command_decorator(b"HVALS")
    def HVALS(self, key: bytes) -> List[bytes]:
        cur = self._hash(key)
        return [] if cur is None else list(cur.values())

    @command_decorator(b"HGETALL")
    def HGETALL(self, key: bytes) -> List[bytes]:
        cur = self._hash(key)
        if cur is None:
            return []
        return [b for a in cur.items() for b in a]

    @command_decorator(b"HSCAN")
    def HSCAN(self, key: bytes, cursor: bytes, *options: bytes):
        """HSCAN key cursor [MATCH pattern] [COUNT n]: one step, like
        SCAN - cursor 0 returns every matching field/value pair and
        cursor 0 again, so keys present for the whole scan are returned
        at least once."""
        parse_scan_cursor(cursor)  # validates, redis' "invalid cursor"
        pattern = parse_scan_options(options)
        rgx = compile_glob(pattern)
        cur = self._hash(key)
        if cur is None:
            return [b"0", []]
        out = []
        for field, value in cur.items():
            if rgx is not None and not rgx.match(field):
                continue
            out.extend((field, value))
        return [b"0", out]

    @command_decorator(b"HINCRBY")
    def HINCRBY(self, key: bytes, field: bytes, increment: int) -> int:
        """64-bit counter on a hash field (HINCRBY key field increment)."""
        cur = self._hash(key)
        if cur is None:
            cur = {}
            self.data[key] = cur

        raw = cur.get(field)
        if raw is None:
            current = 0
        elif not RE_NUMERIC.match(raw):
            raise Errors.HASH_NOT_INT
        else:
            current = int(raw, 10)

        result = current + increment
        if result < INT64_MIN or result > INT64_MAX:
            raise Errors.OVERFLOW
        cur[field] = f"{result}".encode()
        return result
