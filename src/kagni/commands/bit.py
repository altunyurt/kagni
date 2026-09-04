from functools import reduce
from operator import and_, or_, xor

from kagni.constants import Error, Errors
from .common import KIND_BITMAP, expect_kind
from .decorator import command_decorator

__all__ = ["CommandSetMixin"]


def _new_bitmap():
    # pyroaring is imported lazily so the rest of the command set works
    # without the (optional) C extension installed
    from pyroaring import BitMap
    return BitMap()


def _byte_length(max_bit):
    """Number of bytes needed to hold bits ``0..max_bit``, redis-style."""
    return max_bit // 8 + 1


def _universe(bmap):
    """Byte-rounded bit universe of *bmap*: mirrors the length a redis
    string holding the same 1-bits would have."""
    return _byte_length(bmap.max()) * 8


class CommandSetMixin:

    def _bitmap(self, key):
        """Bitmap stored under *key*; None when missing/expired."""
        return expect_kind(self.data, key, KIND_BITMAP)

    @command_decorator(b"SETBIT")
    def SETBIT(self, key: bytes, bit: int, val: int) -> int:
        if bit < 0:
            raise Errors.BIT_OFFSET
        if val not in (0, 1):
            raise Errors.BIT_VALUE

        bmap = self._bitmap(key)
        previous = 0
        if bmap is None:
            bmap = _new_bitmap()
            self.data[key] = bmap
        else:
            previous = 1 if bit in bmap else 0

        if val:
            bmap.add(bit)
        elif previous:
            bmap.remove(bit)
        return previous

    @command_decorator(b"GETBIT")
    def GETBIT(self, key: bytes, bit: int) -> int:
        if bit < 0:
            raise Errors.BIT_OFFSET
        bmap = self._bitmap(key)
        if bmap is None:
            return 0
        return 1 if bit in bmap else 0

    @command_decorator(b"BITOP")
    def BITOP(self, op: bytes, dest_name: bytes, *keys) -> int:
        self._assert_keys(keys, "bitop")
        op = op.upper()

        maps = []
        longest = 0
        for key in keys:
            bmap = self._bitmap(key)
            if bmap is None:
                # a missing key behaves like an empty bitmap operand
                # (matters for AND: anything & empty == empty)
                maps.append(_new_bitmap())
                continue
            maps.append(bmap)
            if len(bmap):
                longest = max(longest, bmap.max())

        if op == b"NOT":
            if len(keys) != 1:
                raise Error("ERR", "BITOP NOT must be called with a single source key")
            source = maps[0]
            if len(source):
                # complement within the byte-rounded universe of the source
                result = source.flip(0, _universe(source))
            else:
                result = _new_bitmap()
        else:
            op_fn = {b"AND": and_, b"OR": or_, b"XOR": xor}.get(op)
            if op_fn is None:
                raise Errors.SYNTAX
            if len(maps) == 1:
                # avoid aliasing the source when there is a single key
                result = maps[0] | _new_bitmap()
            else:
                result = reduce(op_fn, maps[1:], maps[0])

        if len(result):
            self.data[dest_name] = result
        else:
            # redis deletes the destination when the result is empty
            self.data.remove(dest_name)
        return _byte_length(longest) if longest else 0

    @staticmethod
    def _assert_keys(keys, command):
        if not keys:
            raise Errors.arity(command)

    @command_decorator(b"BITCOUNT")
    def BITCOUNT(self, key: bytes) -> int:
        bmap = self._bitmap(key)
        if bmap is None:
            return 0
        return len(bmap)

    @command_decorator(b"BITPOS")
    def BITPOS(self, key: bytes, bit: bytes) -> int:
        if bit not in (b"0", b"1"):
            raise Errors.BIT_ARG

        bmap = self._bitmap(key)
        if bmap is None:
            return -1
        if not len(bmap):
            # nothing stored: only the first-0 question is meaningful
            return 0 if bit == b"0" else -1

        if bit == b"1":
            return bmap.min()

        # first 0 bit: complement inside the byte-rounded universe; an
        # empty complement means the stored range is all 1s -> -1
        complement = bmap.flip(0, _universe(bmap))
        return complement.min() if len(complement) else -1
