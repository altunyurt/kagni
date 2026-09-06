"""Shared helpers for the command mixins.

Value-kind detection powers the Redis WRONGTYPE semantics: every command
checks the kind of the value stored under a key before operating on it,
instead of crashing (or silently returning junk) when types are mixed.
"""

from collections import deque

from kagni.constants import Errors

KIND_STRING = "string"
KIND_HASH = "hash"
KIND_SET = "set"
KIND_BITMAP = "bitmap"
KIND_LIST = "list"

INT64_MIN = -(2 ** 63)
INT64_MAX = 2 ** 63 - 1


def string2ll(raw):
    """Parse a redis-style integer argument (mirrors string2ll in
    util.c): an optional leading '-', plain ASCII digits, no '+', no
    whitespace, no leading zeros (a bare b"0" excepted), and the value
    must fit a signed 64-bit integer.  Raises ValueError otherwise; the
    callers translate that into their per-command NOT_INT / cursor
    errors."""
    if not isinstance(raw, bytes) or not raw:
        raise ValueError
    if raw == b"0":
        return 0
    negative = raw[0] == ord("-")
    digits = raw[1:] if negative else raw
    if not digits or digits[0] == ord("0"):
        raise ValueError  # empty after '-' or a leading zero
    if any(byte < ord("0") or byte > ord("9") for byte in digits):
        raise ValueError
    value = int(digits)
    if negative:
        value = -value
    if value < INT64_MIN or value > INT64_MAX:
        raise ValueError
    return value


def kind_of(value):
    """Name of the kind a stored value belongs to, or None if unknown."""
    # pyroaring is imported lazily by the bit commands; check the class
    # name first (works even when the map is a set-like stand-in) so we
    # never classify a bitmap as a plain set
    if type(value).__name__ == "BitMap":
        return KIND_BITMAP
    if isinstance(value, bytes):
        return KIND_STRING
    if isinstance(value, dict):
        return KIND_HASH
    if isinstance(value, set):
        return KIND_SET
    if isinstance(value, (deque, list)):
        return KIND_LIST
    return None


def expect_kind(data, key, kind):
    """Return the value stored under *key* (None when missing/expired).

    Raise ``Errors.WRONGTYPE`` when the key holds a value of another kind.
    """
    val = data.get(key)
    if val is not None and kind_of(val) != kind:
        raise Errors.WRONGTYPE
    return val
