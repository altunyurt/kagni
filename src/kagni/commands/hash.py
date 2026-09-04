from typing import List

from kagni.constants import Response
from .common import KIND_HASH, expect_kind
from .decorator import command_decorator

__all__ = ["CommandSetMixin"]


class CommandSetMixin:

    def _hash(self, key):
        """Hash stored under *key*; None when missing/expired."""
        return expect_kind(self.data, key, KIND_HASH)

    @command_decorator(b"HSET")
    def HSET(self, key: bytes, field: bytes, val: bytes) -> int:
        cur = self._hash(key)
        if cur is None:
            self.data[key] = {field: val}
            return 1

        is_new = field not in cur
        cur[field] = val
        return 1 if is_new else 0

    @command_decorator(b"HGET")
    def HGET(self, key: bytes, field: bytes) -> (bytes, Response.NIL):
        cur = self._hash(key)
        if cur is None or field not in cur:
            return Response.NIL
        return cur[field]

    @command_decorator(b"HEXISTS")
    def HEXISTS(self, key: bytes, field: bytes) -> int:
        cur = self._hash(key)
        if cur is None or field not in cur:
            return 0
        return 1

    @command_decorator(b"HDEL")
    def HDEL(self, key: bytes, *fields: List[bytes]) -> int:
        cur = self._hash(key)
        if cur is None:
            return 0

        removed = 0
        for field in fields:
            if field in cur:
                del cur[field]
                removed += 1
        return removed

    @command_decorator(b"HGETALL")
    def HGETALL(self, key: bytes) -> List[bytes]:
        cur = self._hash(key)
        if cur is None:
            return []
        return [b for a in cur.items() for b in a]
