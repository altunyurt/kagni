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
