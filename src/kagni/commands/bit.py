import re
from functools import reduce
from operator import and_, or_, xor

from kagni.constants import Error, Errors, Response
from .common import KIND_BITMAP, expect_kind, string2ll
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

# ------------------------------------------------------------ bitfield
# redis parses the type as 'i'/'u' followed by digits; u64 is rejected
# even though i64 works ("Note that u64 is not supported but i64 is")
_BITFIELD_TYPE = re.compile(rb"[iu][0-9]+\Z", re.ASCII)
_BITFIELD_MAX_OFFSET = 2 ** 32 - 1  # the 512 MB string limit, like SETBIT


def _bitfield_type(raw):
    """(signed, width) of a BITFIELD type token, or None when invalid."""
    if not _BITFIELD_TYPE.match(raw):
        return None
    signed = raw[:1] == b"i"
    width = int(raw[1:])
    if width < 1 or width > 64 or (not signed and width == 64):
        return None
    return signed, width


def _extract_bits(bmap, offset, width):
    """Unsigned value of *width* bits at *offset* (MSB first, like the
    byte string redis operates on; absent bits read as 0)."""
    value = 0
    for k in range(width):
        value = (value << 1) | (1 if (offset + k) in bmap else 0)
    return value


def _store_bits(bmap, offset, width, value):
    """Write the low *width* bits of *value* at *offset*."""
    for k in range(width):
        bmap.discard(offset + k)
    bit = offset + width - 1
    while value and bit >= offset:
        if value & 1:
            bmap.add(bit)
        value >>= 1
        bit -= 1


def _interpret(value, signed, width):
    """Signed/unsigned reading of a *width*-bit unsigned value."""
    if signed and value >= 1 << (width - 1):
        value -= 1 << width
    return value


def _bitfield_overflow(value, signed, width, mode):
    """Bring *value* (in the type's domain) into range per the OVERFLOW
    mode; returns (value, ok), ok=False being FAIL (nil, no write)."""
    span = 1 << width
    if signed:
        lo, hi = -(1 << (width - 1)), (1 << (width - 1)) - 1
    else:
        lo, hi = 0, span - 1
    if lo <= value <= hi:
        return value, True
    if mode == b"SAT":
        return (lo if value < lo else hi), True
    if mode == b"WRAP":
        value %= span
        if signed and value >= 1 << (width - 1):
            value -= span
        return value, True
    return 0, False  # FAIL


def _bitfield_offset(raw, width):
    """Bit offset of an offset token: a plain non-negative bit offset or
    '#N' meaning N times the width; redis' offset error otherwise."""
    multiplier = raw[:1] == b"#"
    if multiplier:
        raw = raw[1:]
    try:
        offset = string2ll(raw)
    except ValueError:
        raise Errors.BIT_OFFSET
    if offset < 0 or offset > _BITFIELD_MAX_OFFSET:
        raise Errors.BIT_OFFSET
    return offset * width if multiplier else offset

class CommandSetMixin:

    def _bitmap(self, key):
        """Bitmap stored under *key*; None when missing/expired."""
        return expect_kind(self.data, key, KIND_BITMAP)

    @command_decorator(b"SETBIT")
    def SETBIT(self, key: bytes, bit: int, val: int) -> int:
        # redis caps the offset at 2**32-1 bits (the 512MB string limit)
        if bit < 0 or bit > 2 ** 32 - 1:
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
        if previous != val:
            self._after_write(key, "setbit")
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
            self._after_write(dest_name, "set")
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

    @command_decorator(b"BITFIELD")
    def BITFIELD(self, key: bytes, *args: bytes) -> list:
        return self._bitfield(key, args, ro=False)

    @command_decorator(b"BITFIELD_RO")
    def BITFIELD_RO(self, key: bytes, *args: bytes) -> list:
        return self._bitfield(key, args, ro=True)

    def _bitfield(self, key, args, ro):
        """BITFIELD key [OVERFLOW WRAP|SAT|FAIL] [GET type offset |
        SET type offset value | INCRBY type offset increment] ...

        Subcommands are parsed and validated up front (a bad one fails
        the whole command before anything runs, like redis); at
        execution only an OVERFLOW FAIL can produce an inline nil.
        Values live in the pyroaring bitmap under the key, so SETBIT/
        GETBIT/BITCOUNT all see BITFIELD writes.
        """
        subs = []
        overflow = b"WRAP"
        j = 0
        while j < len(args):
            opt = args[j].upper()
            if opt == b"OVERFLOW":
                if j + 1 >= len(args):
                    raise Errors.SYNTAX
                overflow = args[j + 1].upper()
                if overflow not in (b"WRAP", b"SAT", b"FAIL"):
                    raise Errors.BITFIELD_OVERFLOW
                j += 2
                continue
            if opt not in (b"GET", b"SET", b"INCRBY"):
                raise Errors.SYNTAX
            need = 2 if opt == b"GET" else 3
            if len(args) - j - 1 < need:
                raise Errors.SYNTAX
            rest = args[j + 1:j + 1 + need]
            parsed = _bitfield_type(rest[0])
            if parsed is None:
                raise Errors.BITFIELD_TYPE
            signed, width = parsed
            offset = _bitfield_offset(rest[1], width)
            if opt == b"GET":
                subs.append((b"GET", signed, width, offset, None, None))
            else:
                if ro:
                    raise Errors.BITFIELD_RO
                try:
                    amount = string2ll(rest[2])
                except ValueError:
                    raise Errors.NOT_INT
                subs.append((opt, signed, width, offset, amount, overflow))
            j += 1 + need

        bmap = self._bitmap(key)
        created = bmap is None
        if bmap is None:
            bmap = _new_bitmap()
        out = []
        wrote = False
        for op, signed, width, offset, amount, overflow in subs:
            if op == b"GET":
                out.append(
                    _interpret(_extract_bits(bmap, offset, width), signed, width)
                )
                continue
            if op == b"SET":
                old = _extract_bits(bmap, offset, width)
                value, ok = _bitfield_overflow(amount, signed, width, overflow)
                if ok:
                    _store_bits(bmap, offset, width, value % (1 << width))
                    wrote = True
                out.append(_interpret(old, signed, width) if ok else Response.NIL)
            else:  # INCRBY
                current = _interpret(
                    _extract_bits(bmap, offset, width), signed, width
                )
                value, ok = _bitfield_overflow(
                    current + amount, signed, width, overflow
                )
                if ok:
                    _store_bits(bmap, offset, width, value % (1 << width))
                    wrote = True
                out.append(value if ok else Response.NIL)
        if created and wrote:
            # writes into an existing bitmap already mutated the stored
            # object in place; only a fresh key needs storing
            self.data[key] = bmap
        if wrote:
            self._after_write(key, "setbit")
        return out
