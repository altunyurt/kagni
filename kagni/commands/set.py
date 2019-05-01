from random import randrange, sample
from functools import reduce
from typing import List
import fnmatch
import re
from kagni.constants import Errors, OK, NIL, PONG
from .decorator import command_decorator


__all__ = ["CommandSetMixin"]


class CommandSetMixin:
    @command_decorator(b"SADD")
    def SADD(self, key: bytes, *vals: List[bytes]) -> int:
        if key not in self.data:
            self.data[key] = set()

        initial = len(self.data[key])
        self.data[key].update(set(vals))
        return len(self.data[key]) - initial

    @command_decorator(b"SCARD")
    def SCARD(self, key: bytes) -> int:
        if key not in self.data:
            return 0
        return len(self.data[key])

    @command_decorator(b"SMEMBERS")
    def SMEMBERS(self, key: bytes) -> list:
        if key not in self.data:
            return []

        return list(self.data[key])

    @command_decorator(b"SREM")
    def SREM(self, key: bytes, *val: List[bytes]) -> int:
        if key not in self.data:
            return 0

        initial = len(self.data[key])
        self.data[key] = self.data[key].difference(set(val))
        return initial - len(self.data[key])

    @command_decorator(b"SDIFF")
    def SDIFF(self, *keys: List[bytes]) -> list:
        first = self.data.get(keys[0], set())
        rest = (self.data.get(key, set()) for key in keys[1:])
        retval = reduce(lambda _s1, _s2: _s1 - _s2, rest, first)
        return list(retval)

    @command_decorator(b"SDIFFSTORE")
    def SDIFFSTORE(self, target: bytes, *keys: List[bytes]) -> int:
        first = self.data.get(keys[0], set())
        rest = (self.data.get(key, set()) for key in keys[1:])
        self.data[target] = reduce(lambda _s1, _s2: _s1 - _s2, rest, first)
        return len(self.data[target])

    @command_decorator(b"SINTER")
    def SINTER(self, *keys: List[bytes]) -> list:
        first = self.data.get(keys[0], set())
        rest = (self.data.get(key, set()) for key in keys[1:])
        retval = reduce(lambda _s1, _s2: _s1 & _s2, rest, first)
        return list(retval)

    @command_decorator(b"SINTERSTORE")
    def SINTERSTORE(self, target: bytes, *keys: List[bytes]) -> int:
        first = self.data.get(keys[0], set())
        rest = (self.data.get(key, set()) for key in keys[1:])
        self.data[target] = reduce(lambda _s1, _s2: _s1 & _s2, rest, first)
        return len(self.data[target])

    @command_decorator(b"SISMEMBER")
    def SISMEMBER(self, key: bytes, val: bytes) -> int:
        if key not in self.data:
            return 0
        return 1 if val in self.data[key] else 0

    @command_decorator(b"SMOVE")
    def SMOVE(self, source: bytes, target: bytes, val: bytes) -> int:
        if source not in self.data:
            return 0

        if val not in self.data[source]:
            return 0

        self.data[source].discard(val)
        # this might be different in redis
        if target not in self.data:
            self.data[target] = set()

        self.data[target].add(val)
        return 1

    @command_decorator(b"SPOP")
    def SPOP(self, key: bytes, count: int = None) -> (bytes, List[bytes]):
        if key not in self.data:
            return NIL

        set_len = len(self.data[key])
        count = count if count else 1

        if 1 in (count, set_len):
            return self.data[key].pop()

        if count > set_len:
            return list(self.data[key])

        # vals hashed with random salt, so we could say that the pop would work randomly
        # https://docs.python.org/3.5/reference/datamodel.html#object.__hash__
        return [self.data[key].pop() for i in range(count)]

    @command_decorator(b"SRANDMEMBER")
    def SRANDMEMBER(self, key: bytes, count: int = None) -> (bytes, List[bytes]):
        if key not in self.data:
            return NIL

        set_len = len(self.data[key])
        count = count if count else 1

        if count > set_len > 1:
            return list(self.data[key])

        samples = sample(self.data[key], count)
        if 1 in (count, set_len):
            return samples[0]

        return samples

    @command_decorator(b"SSCAN")
    def SSCAN(self, key: bytes, val: bytes):
        pass

    @command_decorator(b"SUNION")
    def SUNION(self, key: bytes, val: bytes):
        pass

    @command_decorator(b"SUNIONSTORE")
    def SUNIONSTORE(self, key: bytes, val: bytes):
        pass
