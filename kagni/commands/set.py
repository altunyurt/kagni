from random import randrange, sample
from functools import reduce
from typing import List
import fnmatch
import re
from kagni.constants import Errors, Response


__all__ = ["CommandSetMixin"]


class CommandSetMixin:
    def SADD(self, key: bytes, *vals: List[bytes]) -> int:
        if key not in self.data:
            self.data[key] = set()

        initial = len(self.data[key])
        self.data[key].update(set(vals))
        return len(self.data[key]) - initial

    def SCARD(self, key: bytes) -> int:
        if key not in self.data:
            return 0
        return len(self.data[key])

    def SMEMBERS(self, key: bytes) -> list:
        if key not in self.data:
            return []

        return list(self.data[key])

    def SREM(self, key: bytes, *val: List[bytes]) -> int:
        if key not in self.data:
            return 0

        initial = len(self.data[key])
        self.data[key] = self.data[key].difference(set(val))
        return initial - len(self.data[key])

    def SDIFF(self, *keys: List[bytes]) -> list:
        first = self.data.get(keys[0], set())
        rest = (self.data.get(key, set()) for key in keys[1:])
        retval = reduce(lambda _s1, _s2: _s1 - _s2, rest, first)
        return list(retval)

    def SDIFFSTORE(self, target: bytes, *keys: List[bytes]) -> int:
        first = self.data.get(keys[0], set())
        rest = (self.data.get(key, set()) for key in keys[1:])
        self.data[target] = reduce(lambda _s1, _s2: _s1 - _s2, rest, first)
        return len(self.data[target])

    def SINTER(self, *keys: List[bytes]) -> list:
        first = self.data.get(keys[0], set())
        rest = (self.data.get(key, set()) for key in keys[1:])
        retval = reduce(lambda _s1, _s2: _s1 & _s2, rest, first)
        return list(retval)

    def SINTERSTORE(self, target: bytes, *keys: List[bytes]) -> int:
        first = self.data.get(keys[0], set())
        rest = (self.data.get(key, set()) for key in keys[1:])
        self.data[target] = reduce(lambda _s1, _s2: _s1 & _s2, rest, first)
        return len(self.data[target])

    def SISMEMBER(self, key: bytes, val: bytes) -> int:
        if key not in self.data:
            return 0
        return 1 if val in self.data[key] else 0

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

    def SPOP(self, key: bytes, count: int = None) -> (bytes, List[bytes]):
        if key not in self.data:
            return Response.NIL

        set_len = len(self.data[key])
        count = int(count) if count else 1

        if 1 in (count, set_len):
            return self.data[key].pop()

        if count > set_len:
            return list(self.data[key])

        # vals hashed with random salt, so we could say that the pop would work randomly
        # https://docs.python.org/3.5/reference/datamodel.html#object.__hash__
        return [self.data[key].pop() for i in range(count)]

    def SRANDMEMBER(self, key: bytes, count: int = None) -> (bytes, List[bytes]):
        if key not in self.data:
            return Response.NIL

        set_len = len(self.data[key])
        count = int(count) if count else 1

        if count > set_len > 1:
            return list(self.data[key])

        samples = sample(self.data[key], count)
        if 1 in (count, set_len):
            return samples[0]

        return samples

    def SSCAN(self, key: bytes, val: bytes):
        pass

    def SUNION(self, *keys: bytes) -> List[bytes]:
        first = self.data.get(keys[0], set())
        rest = (self.data.get(key, set()) for key in keys[1:])
        retval = reduce(lambda _s1, _s2: _s1 | _s2, rest, first)
        return list(retval)

    def SUNIONSTORE(self, target: bytes, *keys: List[bytes]) -> List[bytes]:
        first = self.data.get(keys[0], set())
        rest = (self.data.get(key, set()) for key in keys[1:])
        self.data[target] = reduce(lambda _s1, _s2: _s1 | _s2, rest, first)
        return len(self.data[target])
