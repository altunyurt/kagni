from random import choice, sample
from functools import reduce
from operator import and_, or_, sub
from typing import List

from kagni.constants import Error, Errors, Response
from .common import (
    KIND_SET,
    compile_glob,
    expect_kind,
    kind_of,
    parse_scan_cursor,
    parse_scan_options,
    string2ll,
)
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

    @staticmethod
    def _assert_members(members, command):
        if not members:
            raise Errors.arity(command)

    @command_decorator(b"SADD")
    def SADD(self, key: bytes, *vals: List[bytes]) -> int:
        self._assert_members(vals, "sadd")
        cur = self._set(key)
        if cur is None:
            self.data[key] = set(vals)
            self._after_write(key, "sadd")
            return len(set(vals))
        before = len(cur)
        cur.update(vals)
        added = len(cur) - before
        if added:
            self._after_write(key, "sadd")
        return added

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
        self._assert_members(val, "srem")
        cur = self._set(key)
        if cur is None:
            return 0

        removed = 0
        for member in val:
            if member in cur:
                cur.discard(member)
                removed += 1
        if removed:
            self._after_write(key, "srem")
        if not cur:
            # redis: the key disappears with its last member
            self.data.remove(key)
            if removed:
                self._notify(key, "del")
        return removed

    @command_decorator(b"SDIFF")
    def SDIFF(self, *keys: List[bytes]) -> list:
        self._assert_keys(keys, "sdiff")
        sets = self._sets(keys)
        result = reduce(sub, sets[1:], set(sets[0]) if sets else set())
        return list(result)

    def _store_result(self, target, result, event):
        """Store a computed set; an empty result deletes the target, like
        redis (empty collections never persist)."""
        if result:
            self.data[target] = result
            self._after_write(target, event)
        else:
            self.data.remove(target)
        return len(result)

    @command_decorator(b"SDIFFSTORE")
    def SDIFFSTORE(self, target: bytes, *keys: List[bytes]) -> int:
        self._assert_keys(keys, "sdiffstore")
        sets = self._sets(keys)
        # copy the first set: the stored result must never alias a source
        result = reduce(sub, sets[1:], set(sets[0]) if sets else set())
        return self._store_result(target, result, "sdiffstore")

    @command_decorator(b"SINTER")
    def SINTER(self, *keys: List[bytes]) -> list:
        self._assert_keys(keys, "sinter")
        sets = self._sets(keys)
        result = reduce(and_, sets[1:], set(sets[0]) if sets else set())
        return list(result)

    @command_decorator(b"SINTERCARD")
    def SINTERCARD(self, numkeys: int, *rest: bytes) -> int:
        """SINTERCARD numkeys key [key ...] [LIMIT limit]: cardinality of
        the intersection (redis 7.0); counting stops once LIMIT is
        reached, LIMIT 0 means no limit."""
        if numkeys < 1:
            raise Error("ERR", "numkeys should be greater than 0")
        if numkeys > len(rest):
            raise Error("ERR", "Number of keys can't be greater than number of args")
        keys = rest[:numkeys]
        limit = 0
        j = numkeys
        while j < len(rest):
            opt = rest[j].upper()
            if opt == b"LIMIT" and j + 1 < len(rest):
                try:
                    limit = string2ll(rest[j + 1])
                except ValueError:
                    limit = -1
                if limit < 0:
                    raise Error("ERR", "LIMIT can't be negative")
                j += 2
            else:
                raise Errors.SYNTAX

        sets = self._sets(keys)  # WRONGTYPE checks, missing -> empty set
        first = sets[0]
        if not first:
            return 0
        # count members of the first set present in every other set,
        # stopping early once LIMIT members are found
        others = sets[1:]
        count = 0
        for member in first:
            if all(member in other for other in others):
                count += 1
                if limit and count >= limit:
                    break
        return count

    @command_decorator(b"SINTERSTORE")
    def SINTERSTORE(self, target: bytes, *keys: List[bytes]) -> int:
        self._assert_keys(keys, "sinterstore")
        sets = self._sets(keys)
        result = reduce(and_, sets[1:], set(sets[0]) if sets else set())
        return self._store_result(target, result, "sinterstore")

    @command_decorator(b"SSCAN")
    def SSCAN(self, key: bytes, cursor: bytes, *options: bytes):
        """SSCAN key cursor [MATCH pattern] [COUNT n]: one step, like
        SCAN (cursor 0 returns every matching member and cursor 0
        again)."""
        parse_scan_cursor(cursor)  # validates, redis' "invalid cursor"
        pattern = parse_scan_options(options)
        rgx = compile_glob(pattern)
        cur = self._set(key)
        if cur is None:
            return [b"0", []]
        out = [member for member in cur if rgx is None or rgx.match(member)]
        return [b"0", out]

    @command_decorator(b"SMISMEMBER")
    def SMISMEMBER(self, key: bytes, *members: bytes) -> list:
        """SMISMEMBER key member [member ...]: one 0/1 slot per member."""
        if not members:
            raise Errors.arity("smismember")
        cur = self._set(key)
        return [1 if cur is not None and member in cur else 0 for member in members]

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
        # the destination is type-checked before the member leaves the
        # source (redis order: a WRONGTYPE target must not lose it)
        dst = self._set(target)
        src.discard(val)
        if dst is None:
            dst = set()
            self.data[target] = dst
        dst.add(val)
        self._after_write(source, "srem")
        if not src:
            # redis: an emptied source disappears
            self.data.remove(source)
            self._notify(source, "del")
        self._after_write(target, "sadd")
        return 1

    @command_decorator(b"SPOP")
    def SPOP(self, key: bytes, count: int = None) -> (bytes, List[bytes]):
        if count is not None and count < 0:
            raise Errors.NOT_POSITIVE

        cur = self._set(key)
        if cur is None or not cur:
            return Response.NIL if count is None else []

        if count is None:
            val = cur.pop()
            self._after_write(key, "spop")
            if not cur:
                # redis: the key disappears with its last member
                self.data.remove(key)
                self._notify(key, "del")
            return val

        if count == 0:
            return []
        if count >= len(cur):
            # popping everything removes the key, like redis
            popped = list(cur)
            self._after_write(key, "spop")
            self.data.remove(key)
            self._notify(key, "del")
            return popped
        self._after_write(key, "spop")
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
        return self._store_result(target, result, "sunionstore")
