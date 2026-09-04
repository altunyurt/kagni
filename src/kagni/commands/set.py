from random import choice, sample
from functools import reduce
from operator import and_, or_, sub
from typing import List

from kagni.constants import Errors, Response
from .common import KIND_SET, expect_kind, kind_of
from .decorator import command_decorator

__all__ = ["CommandSetMixin"]


class CommandSetMixin:

    def _set(self, key):
        """Set stored under *key*; None when missing/expired."""
        return expect_kind(self.data, key, KIND_SET)

    def _sets(self, keys):
        """Set operands for *keys*: a missing/expired key behaves like an
        empty set (matters for SINTER), a key of another kind raises
        WRONGTYPE."""
        sets = []
        for key in keys:
            cur = self.data.get(key)
            if cur is None:
                sets.append(set())
            elif kind_of(cur) != KIND_SET:
                raise Errors.WRONGTYPE
            else:
                sets.append(cur)
        return sets

    @staticmethod
    def _assert_keys(keys, command):
        if not keys:
            raise Errors.arity(command)

    @command_decorator(b"SADD")
    def SADD(self, key: bytes, *vals: List[bytes]) -> int:
        cur = self._set(key)
        if cur is None:
            self.data[key] = set(vals)
            return len(set(vals))
        before = len(cur)
        cur.update(vals)
        return len(cur) - before

    @command_decorator(b"SCARD")
    def SCARD(self, key: bytes) -> int:
        cur = self._set(key)
        if cur is None:
            return 0
        return len(cur)

    @command_decorator(b"SMEMBERS")
    def SMEMBERS(self, key: bytes) -> list:
        cur = self._set(key)
        if cur is None:
            return []
        return list(cur)

    @command_decorator(b"SREM")
    def SREM(self, key: bytes, *val: List[bytes]) -> int:
        cur = self._set(key)
        if cur is None:
            return 0

        removed = 0
        for member in val:
            if member in cur:
                cur.discard(member)
                removed += 1
        return removed

    @command_decorator(b"SDIFF")
    def SDIFF(self, *keys: List[bytes]) -> list:
        self._assert_keys(keys, "sdiff")
        sets = self._sets(keys)
        result = reduce(sub, sets[1:], set(sets[0]) if sets else set())
        return list(result)

    @command_decorator(b"SDIFFSTORE")
    def SDIFFSTORE(self, target: bytes, *keys: List[bytes]) -> int:
        self._assert_keys(keys, "sdiffstore")
        sets = self._sets(keys)
        # copy the first set: the stored result must never alias a source
        result = reduce(sub, sets[1:], set(sets[0]) if sets else set())
        self.data[target] = result
        return len(result)

    @command_decorator(b"SINTER")
    def SINTER(self, *keys: List[bytes]) -> list:
        self._assert_keys(keys, "sinter")
        sets = self._sets(keys)
        result = reduce(and_, sets[1:], set(sets[0]) if sets else set())
        return list(result)

    @command_decorator(b"SINTERSTORE")
    def SINTERSTORE(self, target: bytes, *keys: List[bytes]) -> int:
        self._assert_keys(keys, "sinterstore")
        sets = self._sets(keys)
        result = reduce(and_, sets[1:], set(sets[0]) if sets else set())
        self.data[target] = result
        return len(result)

    @command_decorator(b"SISMEMBER")
    def SISMEMBER(self, key: bytes, val: bytes) -> int:
        cur = self._set(key)
        if cur is None:
            return 0
        return 1 if val in cur else 0

    @command_decorator(b"SMOVE")
    def SMOVE(self, source: bytes, target: bytes, val: bytes) -> int:
        src = self._set(source)
        if src is None:
            return 0
        if val not in src:
            return 0

        src.discard(val)
        dst = self._set(target)
        if dst is None:
            dst = set()
            self.data[target] = dst
        dst.add(val)
        return 1

    @command_decorator(b"SPOP")
    def SPOP(self, key: bytes, count: int = None) -> (bytes, List[bytes]):
        if count is not None and count < 0:
            raise Errors.NOT_POSITIVE

        cur = self._set(key)
        if cur is None or not cur:
            return Response.NIL if count is None else []

        if count is None:
            return cur.pop()

        if count == 0:
            return []
        if count >= len(cur):
            # popping everything keeps redis' guarantee that members are
            # removed; the (now empty) set stays stored like before
            popped = list(cur)
            cur.clear()
            return popped
        return [cur.pop() for _ in range(count)]

    @command_decorator(b"SRANDMEMBER")
    def SRANDMEMBER(self, key: bytes, count: int = None) -> (bytes, List[bytes]):
        cur = self._set(key)
        if cur is None or not cur:
            return Response.NIL if count is None else []

        members = list(cur)
        if count is None:
            return choice(members)

        if count < 0:
            # negative count: sampling with repetition (redis semantics)
            return [choice(members) for _ in range(-count)]
        if count == 0:
            return []
        if count >= len(members):
            return members
        return sample(members, count)

    @command_decorator(b"SUNION")
    def SUNION(self, *keys: bytes) -> List[bytes]:
        self._assert_keys(keys, "sunion")
        sets = self._sets(keys)
        result = reduce(or_, sets[1:], set(sets[0]) if sets else set())
        return list(result)

    @command_decorator(b"SUNIONSTORE")
    def SUNIONSTORE(self, target: bytes, *keys: List[bytes]) -> int:
        self._assert_keys(keys, "sunionstore")
        sets = self._sets(keys)
        result = reduce(or_, sets[1:], set(sets[0]) if sets else set())
        self.data[target] = result
        return len(result)
