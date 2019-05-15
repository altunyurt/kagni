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
    @command_decorator(b"SETBIT")
    def SETBIT(self, key: bytes, bit: int, val: int) -> int:

        ex_val = 0
        bmap = self.data.get(key, BitMap())

        if key not in self.data:
            self.data[key] = bmap
        else:
            ex_val = 1 if bit in bmap else 0

        if val:
            bmap.add(bit)
        elif ex_val:
            bmap.remove(bit)
        return ex_val

    @command_decorator(b"GETBIT")
    def GETBIT(self, key: bytes, bit: int) -> int:
        if key not in self.data:
            return 0

        return 1 if bit in self.data[key] else 0

    @command_decorator(b"BITOP")
    def BITOP(self, op: bytes, dest_name: bytes, *keys) -> int:
        op = op.upper()
        maps = [self.data.get(key, BitMap()) for key in keys]

        self.data[dest_name] = {
            b"AND": partial(reduce, lambda x, y: x & y, maps[1:], maps[0]),
            b"OR": partial(reduce, lambda x, y: x | y, maps[1:], maps[0]),
            b"XOR": partial(reduce, lambda x, y: x ^ y, maps[1:], maps[0]),
            b"NOT": lambda: maps[0].flip(0, maps[0].max()),
        }[op]()

        # redis protocol compatibility. should return the longest string's length
        # but roaring bitmaps only care about 1's. so we'll have to make it up
        max_len = max([self.data.get(i).max() for i in [dest_name, *keys]])
        return ceil(max_len / 8)

    @command_decorator(b"BITCOUNT")
    def BITCOUNT(self, key: bytes) -> int:
        if key not in self.data:
            return 0
        return len(self.data[key])

    @command_decorator(b"BITPOS")
    def BITPOS(self, key: bytes, bit: bytes) -> int:
        retval = -1

        if key not in self.data:
            return retval

        bmap = self.data[key]

        # no bits set yet, so only meaningful for checking 0 bit
        if not len(bmap):
            if bit == b"1":
                retval = -1
            else:
                retval = 0

        else:
            if bit == b"1":
                retval = bmap.min()
            else:
                # xor the bitmap with an all 1s map of same length.
                # min value of the result map is where it's 0 for the original map
                retval = (bmap ^ BitMap(range(bmap.max() + 1))).min()
        return retval
