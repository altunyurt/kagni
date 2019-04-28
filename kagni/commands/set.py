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
    def SDIFF(self, key: bytes, val: bytes):
        pass

    @command_decorator(b"SDIFFSTORE")
    def SDIFFSTORE(self, key: bytes, val: bytes):
        pass

    @command_decorator(b"INTER")
    def INTER(self, key: bytes, val: bytes):
        pass

    @command_decorator(b"SINTERSTORE")
    def SINTERSTORE(self, key: bytes, val: bytes):
        pass

    @command_decorator(b"SISMEMBER")
    def SISMEMBER(self, key: bytes, val: bytes):
        pass

    @command_decorator(b"SMOVE")
    def SMOVE(self, key: bytes, val: bytes):
        pass

    @command_decorator(b"SPOP")
    def SPOP(self, key: bytes, val: bytes):
        pass

    @command_decorator(b"SRANDMEMBER")
    def SRANDMEMBER(self, key: bytes, val: bytes):
        pass

    @command_decorator(b"SSCAN")
    def SSCAN(self, key: bytes, val: bytes):
        pass

    @command_decorator(b"SUNION")
    def SUNION(self, key: bytes, val: bytes):
        pass

    @command_decorator(b"SUNIONSTORE")
    def SUNIONSTORE(self, key: bytes, val: bytes):
        pass
