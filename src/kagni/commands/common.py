"""Shared helpers for the command mixins.

Value-kind detection powers the Redis WRONGTYPE semantics: every command
checks the kind of the value stored under a key before operating on it,
instead of crashing (or silently returning junk) when types are mixed.
The scalar parsers (string2ll, floats) mirror redis' util.c routines so
argument handling is identical across commands.
"""

import fnmatch
import math
import re
from collections import deque

from kagni.constants import Errors
from kagni.zset import ZSet

KIND_STRING = "string"
KIND_HASH = "hash"
KIND_SET = "set"
KIND_BITMAP = "bitmap"
KIND_LIST = "list"
KIND_ZSET = "zset"

INT64_MIN = -(2 ** 63)
INT64_MAX = 2 ** 63 - 1

# non-negative or negative decimal integer, e.g. b"0", b"-42"
RE_NUMERIC = re.compile(rb"-?\d+\Z", re.ASCII)


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


# redis parses floats with libc strtold (string2ld in util.c): the full
# string must parse, no surrounding whitespace, nan rejected; exponents
# and literal inf are accepted here and rejected later when the result
# becomes NaN/Infinity.  Underflow-to-zero (ERANGE) is approximated by
# rejecting non-zero literals that round to 0.0.
def _parse_float(raw):
    try:
        text = raw.decode("ascii")
    except UnicodeDecodeError:
        raise Errors.NOT_FLOAT
    if not text or text != text.strip():
        raise Errors.NOT_FLOAT
    try:
        value = float(text)
    except ValueError:
        raise Errors.NOT_FLOAT
    if math.isnan(value):
        raise Errors.NOT_FLOAT
    if math.isinf(value):
        core = text.lower().lstrip("+-")
        if core not in ("inf", "infinity"):
            raise Errors.NOT_FLOAT  # literal overflow (ERANGE)
    elif value == 0.0 and any(ch in "123456789" for ch in text):
        raise Errors.NOT_FLOAT  # underflow to zero (ERANGE)
    return value


def _format_float(value):
    """Format a float result (zset scores, INCRBYFLOAT).

    redis prints fixed-point with 17 significant long-double digits
    (ld2string LD_STR_HUMAN); python floats are doubles, so the shortest
    round-trip repr is used instead - identical output for the decimal
    values people type (10.5, 0.1+0.2, ...), and exponents for very
    large/small magnitudes.  Integral results lose the trailing '.0'
    and -0 normalises to 0, like redis."""
    text = repr(value)
    if text.endswith(".0"):
        text = text[:-2]
    if text in ("-0",):
        text = "0"
    return text


def compile_glob(pattern):
    """Compile a SCAN-family MATCH pattern (None -> None: match all)."""
    if pattern is None:
        return None
    re_pattern = fnmatch.translate(pattern.decode("utf-8", "surrogateescape"))
    return re.compile(re_pattern.encode("utf-8", "surrogateescape"))


def parse_scan_cursor(raw):
    """Cursor argument of the SCAN family, with redis' errors."""
    try:
        value = string2ll(raw)
    except ValueError:
        raise Errors.INVALID_CURSOR
    if value < 0:
        raise Errors.INVALID_CURSOR
    return value


def parse_scan_options(options):
    """MATCH/COUNT options of the SCAN family (no TYPE, which only the
    keyspace SCAN takes).  Returns the MATCH pattern (None when absent);
    COUNT stays a hint, but must be a positive integer like redis."""
    pattern = None
    j = 0
    while j < len(options):
        opt = options[j].upper()
        if opt in (b"MATCH", b"COUNT") and j + 1 < len(options):
            value = options[j + 1]
            j += 2
            if opt == b"MATCH":
                pattern = value
            else:
                try:
                    count = string2ll(value)
                except ValueError:
                    raise Errors.NOT_INT
                if count < 1:
                    raise Errors.SYNTAX
        else:
            raise Errors.SYNTAX
    return pattern


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
    if isinstance(value, ZSet):
        return KIND_ZSET
    return None


def expect_kind(data, key, kind):
    """Return the value stored under *key* (None when missing/expired).

    Raise ``Errors.WRONGTYPE`` when the key holds a value of another kind.
    """
    val = data.get(key)
    if val is not None and kind_of(val) != kind:
        raise Errors.WRONGTYPE
    return val
