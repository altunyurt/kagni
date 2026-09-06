from typing import List
import fnmatch
import math
import re
import time as _wall

from kagni.constants import Error, Errors, Response, SimpleString
from .common import (
    INT64_MAX,
    INT64_MIN,
    KIND_BITMAP,
    KIND_HASH,
    KIND_LIST,
    KIND_SET,
    KIND_STRING,
    expect_kind,
    kind_of,
    string2ll,
)
from .decorator import command_decorator

# non-negative or negative decimal integer, e.g. b"0", b"-42"
RE_NUMERIC = re.compile(rb"-?\d+\Z", re.ASCII)

# redis-compatible cap for a single string value (proto-max-bulk-len)
MAX_STRING_SIZE = 512 * 1024 * 1024

# parameters exposed through CONFIG GET (redis-benchmark probes these;
# real redis replies with a flat list of alternating name/value pairs)
CONFIG_VALUES = {
    b"maxmemory": b"0",
    b"maxmemory-policy": b"noeviction",
    b"save": b"",
    b"appendonly": b"no",
}


def _config_get(pattern: bytes) -> list:
    """CONFIG GET reply: every matching parameter as name/value pairs,
    or an empty array when nothing matches (redis behaviour)."""
    re_pattern = fnmatch.translate(pattern.decode("utf-8", "surrogateescape"))
    rgx = re.compile(re_pattern.encode("utf-8", "surrogateescape"))
    reply = []
    for name in sorted(CONFIG_VALUES):
        if rgx.match(name):
            reply.extend((name, CONFIG_VALUES[name]))
    return reply

__all__ = ["CommandSetMixin"]


# redis type names for TYPE; bitmaps live in strings in redis, so a
# pyroaring-backed key reports "string" like a SETBIT-created one would
TYPE_NAMES = {
    KIND_STRING: "string",
    KIND_LIST: "list",
    KIND_HASH: "hash",
    KIND_SET: "set",
    KIND_BITMAP: "string",
}


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
    """Format an incrbyfloat result.

    redis prints fixed-point with 17 significant long-double digits
    (ld2string LD_STR_HUMAN); python floats are doubles, so the shortest
    round-trip repr is used instead - identical output for the decimal
    values people type (10.5, 0.1+0.2, ...), and exponents for very
    large/small magnitudes.  Integral results lose the trailing '.0'
    and -0 normalises to 0, like redis.  The stored strings always
    re-parse through _parse_float."""
    text = repr(value)
    if text.endswith(".0"):
        text = text[:-2]
    if text in ("-0",):
        text = "0"
    return text


def _expire_time_error(command):
    """redis: 'invalid expire time in <command> command' (per-command name)."""
    return Error("ERR", "invalid expire time in '%s' command" % command)


def _parse_extended_options(command, options):
    """Parse the SET/GETEX option list, mirroring t_string.c
    parseExtendedStringArgumentsOrReply: NX/XX/GET (SET only),
    KEEPTTL (SET only), PERSIST (GETEX only) and EX/PX/EXAT/PXAT with
    their value.  Duplicates of the same flag/unit are tolerated (last
    one wins), conflicting combinations raise a syntax error.

    Returns ``(flags, unit, raw_value)`` where flags is a set of bytes
    names.
    """
    flags = set()
    unit = None
    raw = None
    is_set = command == "set"
    j = 0
    while j < len(options):
        opt = options[j].upper()
        has_next = j + 1 < len(options)
        if opt == b"NX" and is_set and b"XX" not in flags:
            flags.add(b"NX")
        elif opt == b"XX" and is_set and b"NX" not in flags:
            flags.add(b"XX")
        elif opt == b"GET" and is_set:
            flags.add(b"GET")
        elif (
            opt == b"KEEPTTL"
            and is_set
            and b"PERSIST" not in flags
            and unit is None
        ):
            flags.add(b"KEEPTTL")
        elif (
            opt == b"PERSIST"
            and not is_set
            and b"KEEPTTL" not in flags
            and unit is None
        ):
            flags.add(b"PERSIST")
        elif (
            opt in (b"EX", b"PX", b"EXAT", b"PXAT")
            and b"KEEPTTL" not in flags
            and b"PERSIST" not in flags
            and (unit is None or unit == opt)
            and has_next
        ):
            unit = opt
            j += 1
            raw = options[j]
        else:
            raise Errors.SYNTAX
        j += 1
    return flags, unit, raw


def _expire_wall_deadline(command, unit, raw):
    """Absolute wall-clock deadline (ns) for an EX/PX/EXAT/PXAT value,
    mirroring getExpireMillisecondsOrReply.  Raises NOT_INT for
    non-integers and the per-command expire-time error for non-positive
    or overflowing values."""
    try:
        value = string2ll(raw)
    except ValueError:
        raise Errors.NOT_INT
    if value <= 0:
        raise _expire_time_error(command)
    if unit in (b"EX", b"EXAT") and value > (2 ** 63 - 1) // 1000:
        raise _expire_time_error(command)
    if unit == b"EX":
        value = value * 1000 + _wall.time_ns() // 1_000_000  # s -> ms from now
    elif unit == b"PX":
        value += _wall.time_ns() // 1_000_000  # ms from now
    elif unit == b"EXAT":
        value *= 1000  # absolute seconds -> milliseconds
    # PXAT stays as-is (absolute milliseconds)
    return value * 1_000_000  # wall-clock nanoseconds


class CommandSetMixin:
    @command_decorator(b"PING")
    def PING(self, message: bytes = None) -> (Response.PONG, bytes):
        return message if message is not None else Response.PONG

    @command_decorator(b"COMMAND")
    def COMMAND(self, *args) -> Response.OK:
        return Response.OK

    @command_decorator(b"TYPE")
    def TYPE(self, key: bytes) -> SimpleString:
        val = self.data.get(key)
        if val is None:
            return SimpleString("none")
        return SimpleString(TYPE_NAMES.get(kind_of(val), "none"))

    @command_decorator(b"CLIENT")
    def CLIENT(self, *args: bytes):
        """Minimal CLIENT: stubs for what real clients probe on connect.
        redis-py >= 5 sends CLIENT SETINFO on every connection; names and
        ids are not tracked per connection (stateless server)."""
        if not args:
            raise Errors.arity("client")
        sub = args[0].upper()
        if sub == b"SETINFO" and len(args) == 3:
            return Response.OK
        if sub == b"SETNAME" and len(args) == 2:
            return Response.OK
        if sub == b"GETNAME" and len(args) == 1:
            return b""
        if sub == b"ID" and len(args) == 1:
            return 1
        name = sub.decode("ascii", "replace")
        raise Error(
            "ERR",
            "Unknown subcommand or wrong number of arguments for '{}'. "
            "Try CLIENT HELP.".format(name),
        )

    @command_decorator(b"CONFIG")
    def CONFIG(self, *args: bytes) -> list:
        """Minimal CONFIG: GET is enough for clients that probe the server
        (redis-benchmark fetches ``save`` and ``appendonly`` at startup and
        warns when the reply is missing).

        Values describe kagni honestly: no maxmemory limit, no classic
        snapshot "save" policy (the sqlite dump runs in a worker thread
        and is not fork-based), no appendonly file.
        """
        if not args:
            raise Errors.arity("config")
        subcommand = args[0].upper()
        if subcommand == b"GET":
            if len(args) != 2:
                raise Errors.arity("config|get")
            return _config_get(args[1])
        raise Error(
            "ERR",
            "Unknown CONFIG subcommand or wrong number of arguments for {}".format(
                subcommand.decode("ascii", "replace")
            ),
        )

    # ------------------------------------------------------------- helpers
    def _string(self, key):
        """Value of a string-typed key; None when missing/expired."""
        return expect_kind(self.data, key, KIND_STRING)

    # ------------------------------------------------------------------ core
    @command_decorator(b"SET")
    def SET(self, key: bytes, val: bytes, *options: bytes):
        """SET key value [NX|XX] [GET] [EX s|PX ms|EXAT ts|PXAT ts|KEEPTTL].

        Returns +OK, or the previous value with GET, or NIL when NX/XX
        blocks the write.
        """
        flags, unit, raw = _parse_extended_options("set", options)
        deadline = _expire_wall_deadline("set", unit, raw) if unit else None

        old = self._string(key) if b"GET" in flags else None
        found = key in self.data
        if (b"NX" in flags and found) or (b"XX" in flags and not found):
            # blocked by NX/XX: with GET reply the old value (redis does
            # so even when the write is skipped), otherwise nil
            return old if old is not None else Response.NIL

        # the size guard fires before the write (redis errors and stores
        # nothing; it also does not fire when NX/XX blocked the write)
        if len(val) > MAX_STRING_SIZE:
            raise Errors.STRING_OVERFLOW
        self.data.set(
            key,
            val,
            wall_deadline_ns=deadline,
            keep_ttl=b"KEEPTTL" in flags,
        )
        # with GET the reply is always the old value (or nil when the key
        # did not exist), otherwise +OK
        return old if old is not None else (Response.NIL if b"GET" in flags else Response.OK)

    @command_decorator(b"SETNX")
    def SETNX(self, key: bytes, val: bytes) -> int:
        if key in self.data:
            return 0
        if len(val) > MAX_STRING_SIZE:
            raise Errors.STRING_OVERFLOW
        self.data.set(key, val)
        return 1

    @command_decorator(b"SETEX")
    def SETEX(self, key: bytes, secs: int, val: bytes) -> Response.OK:
        deadline = _expire_wall_deadline("setex", b"EX", str(secs).encode())
        self.data.set(key, val, wall_deadline_ns=deadline)
        return Response.OK

    @command_decorator(b"PSETEX")
    def PSETEX(self, key: bytes, ms: int, val: bytes) -> Response.OK:
        deadline = _expire_wall_deadline("psetex", b"PX", str(ms).encode())
        self.data.set(key, val, wall_deadline_ns=deadline)
        return Response.OK

    @command_decorator(b"GET")
    def GET(self, key: bytes) -> (bytes, Response.NIL):
        val = self._string(key)
        return Response.NIL if val is None else val

    @command_decorator(b"GETDEL")
    def GETDEL(self, key: bytes) -> (bytes, Response.NIL):
        val = self._string(key)
        if val is None:
            return Response.NIL
        self.data.remove(key)
        return val

    @command_decorator(b"GETEX")
    def GETEX(self, key: bytes, *options: bytes):
        """GETEX key [PERSIST|EX s|PX ms|EXAT ts|PXAT ts].  Returns the
        value and updates its TTL; NIL for a missing key."""
        flags, unit, raw = _parse_extended_options("getex", options)

        val = self._string(key)
        if val is None:
            return Response.NIL

        if b"PERSIST" in flags:
            self.data.persist(key)
        elif unit:
            deadline = _expire_wall_deadline("getex", unit, raw)
            if deadline <= _wall.time_ns():
                # EXAT/PXAT in the past: redis replies the value and deletes
                self.data.remove(key)
            else:
                self.data.set(key, val, wall_deadline_ns=deadline)
        return val

    @command_decorator(b"GETSET")
    def GETSET(self, key: bytes, val: bytes) -> (bytes, Response.NIL):
        retval = self._string(key)
        if len(val) > MAX_STRING_SIZE:
            raise Errors.STRING_OVERFLOW
        self.data[key] = val
        return Response.NIL if retval is None else retval

    @command_decorator(b"MGET")
    def MGET(self, *keys) -> list:
        if not keys:
            raise Errors.arity("mget")
        out = []
        for key in keys:
            val = self._string(key)
            out.append(Response.NIL if val is None else val)
        return out

    @command_decorator(b"MSET")
    def MSET(self, *args: bytes) -> Response.OK:
        if len(args) < 2 or len(args) % 2:
            raise Errors.arity("mset")
        for value in args[1::2]:
            if len(value) > MAX_STRING_SIZE:
                raise Errors.STRING_OVERFLOW
        self.data.update(zip(args[::2], args[1::2]))
        return Response.OK

    @command_decorator(b"MSETNX")
    def MSETNX(self, *args: bytes) -> int:
        if len(args) < 2 or len(args) % 2:
            raise Errors.arity("msetnx")
        keys = args[::2]
        if any(key in self.data for key in keys):
            return 0  # nothing is set when at least one key exists
        for value in args[1::2]:
            if len(value) > MAX_STRING_SIZE:
                raise Errors.STRING_OVERFLOW
        self.data.update(zip(keys, args[1::2]))
        return 1

    @command_decorator(b"DEL")
    def DEL(self, *keys) -> int:
        if not keys:
            raise Errors.arity("del")
        return sum(self.data.remove(key) for key in keys)

    @command_decorator(b"EXPIRE")
    def EXPIRE(self, key: bytes, secs: int) -> int:
        return self.data.expire(key, secs)

    @command_decorator(b"PERSIST")
    def PERSIST(self, key: bytes) -> int:
        return self.data.persist(key)

    @command_decorator(b"TTL")
    def TTL(self, key: bytes) -> int:
        return self.data.ttl(key)

    @command_decorator(b"KEYS")
    def KEYS(self, pattern: bytes) -> List[bytes]:
        # surrogateescape keeps raw (non-utf8) patterns and keys working
        re_pattern = fnmatch.translate(
            pattern.decode("utf-8", "surrogateescape")
        )
        rgx = re.compile(re_pattern.encode("utf-8", "surrogateescape"))
        return [key for key in self.data if rgx.match(key)]

    # ------------------------------------------------------------- keyspace
    @command_decorator(b"SCAN")
    def SCAN(self, cursor: bytes, *options: bytes):
        """SCAN cursor [MATCH pattern] [COUNT n] [TYPE type]

        kagni returns the whole snapshot in one step: cursor 0 yields
        every matching key and cursor 0 again, which satisfies the redis
        guarantee that keys present for the whole scan are returned at
        least once.  COUNT is only a hint (ignored); TYPE filters by the
        TYPE command's names.
        """
        try:
            cursor_value = string2ll(cursor)
        except ValueError:
            raise Errors.INVALID_CURSOR
        if cursor_value < 0:
            raise Errors.INVALID_CURSOR
        if cursor_value != 0:
            # kagni never emits non-zero cursors: treat any other value
            # as an already-finished iteration
            return [b"0", []]

        pattern = None
        type_filter = None
        j = 0
        while j < len(options):
            opt = options[j].upper()
            if opt in (b"MATCH", b"COUNT", b"TYPE") and j + 1 < len(options):
                value = options[j + 1]
                j += 2
                if opt == b"MATCH":
                    pattern = value
                elif opt == b"COUNT":
                    try:
                        count = string2ll(value)
                    except ValueError:
                        raise Errors.NOT_INT
                    if count < 1:
                        # redis rejects non-positive COUNT with a syntax
                        # error even though the value is only a hint
                        raise Errors.SYNTAX
                else:
                    type_filter = value.lower().decode("ascii", "replace")
            else:
                raise Errors.SYNTAX

        if pattern is not None:
            re_pattern = fnmatch.translate(
                pattern.decode("utf-8", "surrogateescape")
            )
            rgx = re.compile(re_pattern.encode("utf-8", "surrogateescape"))
        else:
            rgx = None

        keys = []
        for key in list(self.data):
            if rgx is not None and not rgx.match(key):
                continue
            if type_filter is not None:
                val = self.data.get(key)
                if val is None:
                    continue
                if TYPE_NAMES.get(kind_of(val)) != type_filter:
                    continue
            keys.append(key)
        return [b"0", keys]

    @command_decorator(b"EXISTS")
    def EXISTS(self, *keys) -> int:
        if not keys:
            raise Errors.arity("exists")
        return sum(1 for key in keys if key in self.data)

    @command_decorator(b"TOUCH")
    def TOUCH(self, *keys) -> int:
        if not keys:
            raise Errors.arity("touch")
        return sum(1 for key in keys if key in self.data)

    @command_decorator(b"DBSIZE")
    def DBSIZE(self) -> int:
        return len(self.data)

    # ----------------------------------------------------------- counters
    def _bump(self, key, by):
        """Shared INCR/INCRBY/DECR/DECRBY implementation."""
        val = self.data.get(key)
        if val is None:
            current = 0
        elif kind_of(val) != KIND_STRING:
            raise Errors.WRONGTYPE
        elif not RE_NUMERIC.match(val):
            raise Errors.NOT_INT
        else:
            current = int(val, 10)

        result = current + by
        if result < INT64_MIN or result > INT64_MAX:
            raise Errors.OVERFLOW
        # keep_ttl: redis counters update the value without touching the
        # key's expiration (only the SET family clears TTLs)
        self.data.set(key, f"{result}".encode(), keep_ttl=True)
        return result

    @command_decorator(b"INCRBY")
    def INCRBY(self, key: bytes, i: int) -> int:
        return self._bump(key, i)

    @command_decorator(b"INCR")
    def INCR(self, key: bytes) -> int:
        return self._bump(key, 1)

    @command_decorator(b"INCRBYFLOAT")
    def INCRBYFLOAT(self, key: bytes, increment: bytes) -> bytes:
        # redis type-checks the key before parsing either value
        val = self._string(key)
        current = _parse_float(val) if val is not None else 0.0
        incr = _parse_float(increment)

        result = current + incr
        if not math.isfinite(result):
            raise Errors.FLOAT_OVERFLOW
        text = _format_float(result)
        # keep_ttl: like INCR, INCRBYFLOAT leaves an existing TTL alone
        self.data.set(key, text.encode(), keep_ttl=True)
        return text.encode()

    @command_decorator(b"DECRBY")
    def DECRBY(self, key: bytes, i: int) -> int:
        return self._bump(key, -i)

    @command_decorator(b"DECR")
    def DECR(self, key: bytes) -> int:
        return self._bump(key, -1)

    # -------------------------------------------------------------- ranges
    @command_decorator(b"GETRANGE")
    def GETRANGE(self, key: bytes, start: int, end: int) -> bytes:
        val = self._string(key)
        if val is None:
            return b""
        # redis-style inclusive end, supporting negative offsets: convert
        # to a python slice end (exclusive, relative to the length)
        stop = end + 1 if end >= 0 else len(val) + end + 1
        return val[start:stop]

    @command_decorator(b"SETRANGE")
    def SETRANGE(self, key: bytes, offset: int, value: bytes) -> int:
        if offset < 0:
            raise Errors.RANGE_OFFSET
        val = self._string(key)
        if val is None:
            val = b""
        if offset + len(value) > MAX_STRING_SIZE:
            raise Errors.STRING_OVERFLOW

        if offset > len(val):
            val = val.ljust(offset, b"\x00") + value
        else:
            val = val[:offset] + value + val[offset + len(value):]
        # keep_ttl: SETRANGE edits the string in place in redis and leaves
        # an existing TTL alone (unlike SET/GETSET)
        self.data.set(key, val, keep_ttl=True)
        return len(val)

    # ---------------------------------------------------------------- misc
    @command_decorator(b"FLUSHDB")
    def FLUSHDB(self):
        return self._flush_all()

    @command_decorator(b"FLUSHALL")
    def FLUSHALL(self):
        return self._flush_all()

    def _flush_all(self):
        """Empty the store and the persisted snapshot.

        The store is cleared in place - not swapped for a fresh Data - so
        the snapshot dumper tasks (which hold a reference to this object)
        keep seeing the emptied store; the epoch bump inside clear()
        makes any snapshot taken before the flush fail its commit guard.
        The wipe must run after clear() so stale commits stand down.
        """
        self.data.clear()
        if self.persistence is not None:
            self.persistence.flush()
        return Response.OK

    @command_decorator(b"APPEND")
    def APPEND(self, key: bytes, val: bytes) -> int:
        current = self._string(key)
        value = (current if current is not None else b"") + val
        if len(value) > MAX_STRING_SIZE:
            raise Errors.STRING_OVERFLOW
        # keep_ttl: redis APPEND appends in place and leaves an existing
        # TTL alone
        self.data.set(key, value, keep_ttl=True)
        return len(value)

    @command_decorator(b"STRLEN")
    def STRLEN(self, key: bytes) -> int:
        val = self._string(key)
        return len(val) if val is not None else 0
