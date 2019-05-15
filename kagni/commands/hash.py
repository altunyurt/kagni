from typing import List
from functools import partial, reduce
from math import ceil 
from pyroaring import BitMap
import fnmatch
import re

from kagni.constants import Errors, Response
from .decorator import command_decorator

__all__ = ["CommandSetMixin"]

class CommandSetMixin:

    @command_decorator(b"HSET")
    def HSET(self, key: bytes, field: bytes, val: bytes) -> int:
        retval = 0  # field is new

        if key not in self.data:
            self.data[key] = {}
            retval = 1
        elif field not in self.data[key]:
            retval = 1

        self.data[key][field] = val
        return retval

    @command_decorator(b"HGET")
    def HGET(self, key: bytes, field: bytes) -> (bytes, Response.NIL):
        data = self.data
        if key not in data:
            return Response.NIL

        if field not in data[key]:
            return Response.NIL

        return data[key][field]

    @command_decorator(b"HEXISTS")
    def HEXISTS(self, key: bytes, field: bytes) -> int:
        data = self.data
        if key not in data:
            return 0

        if field not in data[key]:
            return 0

        return 1

    @command_decorator(b"HDEL")
    def HDEL(self, key: bytes, *fields: List[bytes]) -> int:
        if key not in self.data:
            return 0

        data = self.data[key]
        retval = 0
        for field in fields:
            if field not in data:
                continue
            del data[field]
            retval += 1
        return retval

    @command_decorator(b"HGETALL")
    def HGETALL(self, key: bytes) -> List[bytes]:
        if key not in self.data:
            return []
        data = self.data[key]
        return [b for a in data.items() for b in a]

