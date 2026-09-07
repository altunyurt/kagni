"""Redis hash commands (redis 7.4 semantics, field expiries included).

Storage: a plain dict {field: bytes} exactly like a hash without
field-level TTLs; once HEXPIRE-family touches a field its entry becomes
a ``(value, wall_deadline_ns)`` tuple (the deadline is wall-clock so
snapshots persist it as-is and restores need no conversion).  All reads
treat expired fields as missing and purge them lazily; a hash whose last
field expires or is deleted disappears, like every empty collection.

The HEXPIRE family follows redis' batch grammar (``FIELDS numfields
field ...`` with per-field array replies) and its tri-state results:
1 = expiry set, 0 = blocked by NX/XX/GT/LT, 2 = field deleted by a
non-positive or past deadline, -2 = field (or key) missing.
"""

import math
import time as _wall
from random import choice, sample
from typing import List

from kagni.constants import Error, Errors, Response
from .common import (
    INT64_MAX,
    INT64_MIN,
    KIND_HASH,
    RE_NUMERIC,
    _format_float,
    _parse_float,
    compile_glob,
    expect_kind,
    parse_scan_cursor,
    parse_scan_options,
    string2ll,
)
from .decorator import command_decorator

__all__ = ["CommandSetMixin"]

# redis stores field expiries as absolute millisecond timestamps below
# this ceiling (verified live: 2**46 - 1 passes, 2**46 fails)
_FIELD_TTL_MAX_MS = 2 ** 46 - 1

# per-command timeout text, redis' "invalid expire time in '<cmd>' command"
_FIELD_TTL_COMMANDS = {
    "hexpire": 10 ** 9,    # seconds
    "hexpireat": 10 ** 9,
    "hpexpire": 10 ** 6,   # milliseconds
    "hpexpireat": 10 ** 6,
}


class CommandSetMixin:

    def _hash(self, key):
        """Hash stored under *key*; None when missing/expired."""
        return expect_kind(self.data, key, KIND_HASH)

    # -------------------------------------------------- field expiry model
    @staticmethod
    def _entry(raw):
        """(value, wall_deadline_ns or None) of a stored field entry."""
        if isinstance(raw, tuple):
            return raw[0], raw[1]
        return raw, None

    @staticmethod
    def _put(cur, field, value, deadline=None):
        if deadline is None:
            cur[field] = value
        else:
            cur[field] = (value, deadline)

    def _field(self, cur, field):
        """(value, deadline) of a live field, or None; an expired field
        is purged on the way (lazily, like redis)."""
        raw = cur.get(field)
        if raw is None:
            return None
        value, deadline = self._entry(raw)
        if deadline is not None and deadline <= _wall.time_ns():
            del cur[field]
            return None
        return value, deadline

    def _purge(self, cur):
        """Drop every expired field; returns how many were dropped."""
        now = _wall.time_ns()
        dead = [
            field
            for field, raw in cur.items()
            if isinstance(raw, tuple) and raw[1] is not None and raw[1] <= now
        ]
        for field in dead:
            del cur[field]
        return len(dead)

    def _live_pairs(self, cur):
        """[(field, value, deadline)] of the live fields, expired ones
        purged in the same pass."""
        self._purge(cur)
        return [(field, value, deadline) for field, raw in cur.items()
                for value, deadline in (self._entry(raw),)]

    def _drop_if_empty(self, key, cur):
        if not cur:
            self.data.remove(key)

    # --------------------------------------------------------------- writes
    @command_decorator(b"HSET")
    def HSET(self, key: bytes, *field_values: bytes) -> int:
        """HSET key field value [field value ...] (variadic since redis
        4.0); replies with the number of fields that were newly added.
        Setting a field clears any field-level TTL, like redis."""
        if len(field_values) < 2 or len(field_values) % 2:
            raise Errors.arity("hset")
        return self._hset_pairs(key, field_values)

    @command_decorator(b"HMSET")
    def HMSET(self, key: bytes, *field_values: bytes) -> Response.OK:
        """HMSET key field value [field value ...] (deprecated alias of
        HSET that replies +OK instead of the field count)."""
        if len(field_values) < 2 or len(field_values) % 2:
            raise Errors.arity("hmset")
        self._hset_pairs(key, field_values)
        return Response.OK

    def _hset_pairs(self, key, field_values):
        """Apply field/value pairs to the hash under *key*; returns how
        many fields were newly added (an expired field counts as new)."""
        cur = self._hash(key)
        if cur is None:
            cur = {}
            self.data[key] = cur
        new_fields = 0
        for i in range(0, len(field_values), 2):
            field, value = field_values[i], field_values[i + 1]
            if self._field(cur, field) is None:
                new_fields += 1
            self._put(cur, field, value)  # a SET always clears the TTL
        self._after_write(key, "hset")
        return new_fields

    @command_decorator(b"HSETNX")
    def HSETNX(self, key: bytes, field: bytes, val: bytes) -> int:
        """HSETNX key field value: set only when the field is missing."""
        cur = self._hash(key)
        if cur is not None and self._field(cur, field) is not None:
            return 0
        if cur is None:
            cur = {}
            self.data[key] = cur
        self._put(cur, field, val)
        self._after_write(key, "hset")
        return 1

    # ---------------------------------------------------------------- reads
    @command_decorator(b"HGET")
    def HGET(self, key: bytes, field: bytes) -> (bytes, Response.NIL):
        cur = self._hash(key)
        if cur is None:
            return Response.NIL
        live = self._field(cur, field)
        if live is None:
            return Response.NIL
        return live[0]

    @command_decorator(b"HMGET")
    def HMGET(self, key: bytes, *fields: bytes) -> list:
        """HMGET key field [field ...]: one reply slot per requested
        field, nil for missing fields and for a missing key alike."""
        if not fields:
            raise Errors.arity("hmget")
        cur = self._hash(key)
        out = []
        for field in fields:
            live = self._field(cur, field) if cur is not None else None
            out.append(Response.NIL if live is None else live[0])
        return out

    @command_decorator(b"HEXISTS")
    def HEXISTS(self, key: bytes, field: bytes) -> int:
        cur = self._hash(key)
        if cur is None:
            return 0
        return 1 if self._field(cur, field) is not None else 0

    @command_decorator(b"HDEL")
    def HDEL(self, key: bytes, *fields: List[bytes]) -> int:
        if not fields:
            raise Errors.arity("hdel")
        cur = self._hash(key)
        if cur is None:
            return 0

        removed = 0
        for field in fields:
            if self._field(cur, field) is not None:
                del cur[field]
                removed += 1
        if removed:
            self._after_write(key, "hdel")
        if not cur:
            # redis: the key disappears with its last field
            self.data.remove(key)
            if removed:
                self._notify(key, "del")
        return removed

    @command_decorator(b"HLEN")
    def HLEN(self, key: bytes) -> int:
        cur = self._hash(key)
        if cur is None:
            return 0
        count = len(self._live_pairs(cur))
        self._drop_if_empty(key, cur)
        return count

    @command_decorator(b"HKEYS")
    def HKEYS(self, key: bytes) -> List[bytes]:
        cur = self._hash(key)
        if cur is None:
            return []
        keys = [field for field, _, _ in self._live_pairs(cur)]
        self._drop_if_empty(key, cur)
        return keys

    @command_decorator(b"HVALS")
    def HVALS(self, key: bytes) -> List[bytes]:
        cur = self._hash(key)
        if cur is None:
            return []
        vals = [value for _, value, _ in self._live_pairs(cur)]
        self._drop_if_empty(key, cur)
        return vals

    @command_decorator(b"HGETALL")
    def HGETALL(self, key: bytes) -> List[bytes]:
        cur = self._hash(key)
        if cur is None:
            return []
        pairs = self._live_pairs(cur)
        self._drop_if_empty(key, cur)
        return [b for pair in pairs for b in (pair[0], pair[1])]

    @command_decorator(b"HSTRLEN")
    def HSTRLEN(self, key: bytes, field: bytes) -> int:
        cur = self._hash(key)
        if cur is None:
            return 0
        live = self._field(cur, field)
        return 0 if live is None else len(live[0])

    @command_decorator(b"HSCAN")
    def HSCAN(self, key: bytes, cursor: bytes, *options: bytes):
        """HSCAN key cursor [MATCH pattern] [COUNT n]: one step, like
        SCAN - cursor 0 returns every matching field/value pair and
        cursor 0 again, so keys present for the whole scan are returned
        at least once."""
        parse_scan_cursor(cursor)  # validates, redis' "invalid cursor"
        pattern = parse_scan_options(options)
        rgx = compile_glob(pattern)
        cur = self._hash(key)
        if cur is None:
            return [b"0", []]
        out = []
        for field, value, _ in self._live_pairs(cur):
            if rgx is not None and not rgx.match(field):
                continue
            out.extend((field, value))
        self._drop_if_empty(key, cur)
        return [b"0", out]

    @command_decorator(b"HRANDFIELD")
    def HRANDFIELD(self, key: bytes, count: int = None, *options: bytes):
        """HRANDFIELD key [count [WITHVALUES]]: random fields, like
        SRANDMEMBER but over a hash; WITHVALUES appends each field's
        value."""
        if count is None:
            if options:
                raise Errors.SYNTAX
            cur = self._hash(key)
            if cur is None:
                return Response.NIL
            pairs = self._live_pairs(cur)
            self._drop_if_empty(key, cur)
            if not pairs:
                return Response.NIL
            return choice(pairs)[0]

        withvalues = False
        for option in options:
            if option.upper() == b"WITHVALUES":
                withvalues = True
            else:
                raise Errors.SYNTAX

        cur = self._hash(key)
        if cur is None:
            return []
        pairs = self._live_pairs(cur)
        self._drop_if_empty(key, cur)
        if not pairs:
            return []
        if count < 0:
            picked = [choice(pairs) for _ in range(-count)]
        elif count == 0:
            picked = []
        elif count >= len(pairs):
            picked = pairs
        else:
            picked = sample(pairs, count)
        if not withvalues:
            return [field for field, _, _ in picked]
        out = []
        for field, value, _ in picked:
            out.extend((field, value))
        return out

    # ------------------------------------------------------------- counters
    @command_decorator(b"HINCRBY")
    def HINCRBY(self, key: bytes, field: bytes, increment: int) -> int:
        """64-bit counter on a hash field; an existing field-level TTL
        survives the update, like redis (only HSET clears it)."""
        cur = self._hash(key)
        if cur is None:
            cur = {}
            self.data[key] = cur
        live = self._field(cur, field)
        if live is None:
            current, deadline = 0, None
        else:
            raw = live[0]
            if not RE_NUMERIC.match(raw):
                raise Errors.HASH_NOT_INT
            current, deadline = int(raw, 10), live[1]

        result = current + increment
        if result < INT64_MIN or result > INT64_MAX:
            raise Errors.OVERFLOW
        self._put(cur, field, f"{result}".encode(), deadline)
        self._after_write(key, "hincrby")
        return result

    @command_decorator(b"HINCRBYFLOAT")
    def HINCRBYFLOAT(self, key: bytes, field: bytes, increment: bytes) -> bytes:
        """HINCRBYFLOAT key field increment: double counter on a field."""
        increment = _parse_float(increment)  # nan -> NOT_FLOAT, like redis
        if not math.isfinite(increment):
            # redis rejects literal inf increments at parse time
            raise Errors.HASH_NAN_OR_INF
        cur = self._hash(key)
        if cur is None:
            cur = {}
            self.data[key] = cur
        live = self._field(cur, field)
        if live is None:
            current, deadline = 0.0, None
        else:
            try:
                current = _parse_float(live[0])
            except Error:
                raise Errors.HASH_NOT_FLOAT
            deadline = live[1]
        result = current + increment
        # a non-finite *result* (e.g. stored inf + 1) uses the key-level
        # INCRBYFLOAT wording
        if not math.isfinite(result):
            raise Errors.FLOAT_OVERFLOW
        text = _format_float(result)
        self._put(cur, field, text.encode(), deadline)
        self._after_write(key, "hincrbyfloat")
        return text.encode()

    # ---------------------------------------------- field-level expiries
    @command_decorator(b"HEXPIRE")
    def HEXPIRE(self, key: bytes, *args: bytes):
        return self._hexpire(key, args, "hexpire")

    @command_decorator(b"HPEXPIRE")
    def HPEXPIRE(self, key: bytes, *args: bytes):
        return self._hexpire(key, args, "hpexpire")

    @command_decorator(b"HEXPIREAT")
    def HEXPIREAT(self, key: bytes, *args: bytes):
        return self._hexpire(key, args, "hexpireat")

    @command_decorator(b"HPEXPIREAT")
    def HPEXPIREAT(self, key: bytes, *args: bytes):
        return self._hexpire(key, args, "hpexpireat")

    def _parse_field_ttl_args(self, args, command):
        """HEXPIRE key time [NX|XX|GT|LT] FIELDS numfields field...
        Returns (when_ms, flags, fields)."""
        if len(args) < 1:
            raise Errors.arity(command)
        try:
            when = string2ll(args[0])
        except ValueError:
            raise Errors.NOT_INT
        if when < 0:
            raise Error("ERR", "invalid expire time, must be >= 0")
        unit = _FIELD_TTL_COMMANDS[command]
        absolute = command in ("hexpireat", "hpexpireat")
        when_ms = when * (1000 if unit == 10 ** 9 else 1)
        now_ms = _wall.time_ns() // 10 ** 6
        ceiling = _FIELD_TTL_MAX_MS if absolute else _FIELD_TTL_MAX_MS - now_ms
        if when_ms > ceiling:
            raise Error(
                "ERR", "invalid expire time in '%s' command" % command
            )

        nx = xx = gt = lt = False
        flags_seen = 0
        j = 1
        while j < len(args):
            opt = args[j].upper()
            if opt == b"FIELDS":
                break
            # redis allows at most one NX/XX/GT/LT token: a second flag
            # (even a duplicate) or any other token means FIELDS is not
            # at the right position
            if opt in (b"NX", b"XX", b"GT", b"LT") and not flags_seen:
                nx, xx, gt, lt = (
                    opt == b"NX", opt == b"XX", opt == b"GT", opt == b"LT"
                )
                flags_seen = 1
            else:
                raise Error(
                    "ERR",
                    "Mandatory argument FIELDS is missing or not at the "
                    "right position",
                )
            j += 1
        if j >= len(args):
            raise Errors.arity(command)  # FIELDS never appeared
        if j + 1 >= len(args):
            raise Errors.arity(command)
        try:
            numfields = string2ll(args[j + 1])
        except ValueError:
            raise Error("ERR", "Parameter `numFields` should be greater than 0")
        if numfields == 0:
            raise Errors.arity(command)
        if numfields < 0:
            raise Error("ERR", "Parameter `numFields` should be greater than 0")
        fields = args[j + 2:j + 2 + numfields]
        if len(fields) != numfields or j + 2 + numfields != len(args):
            # a count mismatch or any leftover token is the same error
            raise Error(
                "ERR",
                "The `numfields` parameter must match the number of arguments",
            )
        return when_ms, (nx, xx, gt, lt), fields

    def _hexpire(self, key, args, command):
        when_ms, (nx, xx, gt, lt), fields = self._parse_field_ttl_args(
            args, command
        )
        absolute = command in ("hexpireat", "hpexpireat")
        cur = self._hash(key)
        out = []
        if cur is None:
            return [-2] * len(fields)
        for field in fields:
            live = self._field(cur, field)
            if live is None:
                out.append(-2)  # missing (or already expired) field
                continue
            value, deadline = live
            now_ms = _wall.time_ns() // 10 ** 6
            if absolute:
                new_deadline = when_ms * 10 ** 6
            else:
                new_deadline = _wall.time_ns() + when_ms * 10 ** 6
            has_ttl = deadline is not None
            if nx and has_ttl:
                out.append(0)
                continue
            if xx and not has_ttl:
                out.append(0)
                continue
            if gt:
                if has_ttl and new_deadline <= deadline:
                    out.append(0)
                    continue
            if lt:
                if has_ttl and new_deadline >= deadline:
                    out.append(0)
                    continue
                if not has_ttl:
                    out.append(0)
                    continue
            if new_deadline <= _wall.time_ns():
                # zero/past: the field is deleted (redis replies 2)
                del cur[field]
                out.append(2)
                continue
            self._put(cur, field, value, new_deadline)
            out.append(1)
        if any(result in (1, 2) for result in out):
            self._after_write(key, "hexpire")
            if not cur:
                self._notify(key, "del")
        self._drop_if_empty(key, cur)
        return out

    def _hexpire_read(self, key, args, command, kind):
        """Shared HTTL/HPTTL/HPERSIST/HEXPIRETIME/HPEXPIRETIME: per-field
        array replies, batch FIELDS grammar."""
        if len(args) < 2:
            raise Errors.arity(command)
        if args[0].upper() != b"FIELDS":
            raise Errors.arity(command)
        try:
            numfields = string2ll(args[1])
        except ValueError:
            raise Error("ERR", "Number of fields must be a positive integer")
        if numfields == 0:
            raise Errors.arity(command)
        if numfields < 0:
            raise Error("ERR", "Number of fields must be a positive integer")
        fields = args[2:2 + numfields]
        if len(fields) != numfields or 2 + numfields != len(args):
            raise Error(
                "ERR",
                "The `numfields` parameter must match the number of arguments",
            )
        cur = self._hash(key)
        out = []
        now = _wall.time_ns()
        persisted = 0
        for field in fields:
            live = self._field(cur, field) if cur is not None else None
            if live is None:
                out.append(-2)
                continue
            value, deadline = live
            if kind == "persist":
                if deadline is None:
                    out.append(-1)
                else:
                    self._put(cur, field, value)
                    out.append(1)
                    persisted += 1
                continue
            if deadline is None:
                out.append(-1)
                continue
            if kind == "ttl":
                ms = -((deadline - now) // -10 ** 6)  # ceil
                out.append((ms + 500) // 1000)
            elif kind == "pttl":
                out.append(-((deadline - now) // -10 ** 6))
            elif kind == "expiretime":
                out.append(deadline // 10 ** 9)
            else:  # pexpiretime
                out.append(deadline // 10 ** 6)
        if persisted:
            self._after_write(key, "hpersist")
        self._drop_if_empty(key, cur)
        return out

    @command_decorator(b"HTTL")
    def HTTL(self, key: bytes, *args: bytes):
        return self._hexpire_read(key, args, "httl", "ttl")

    @command_decorator(b"HPTTL")
    def HPTTL(self, key: bytes, *args: bytes):
        return self._hexpire_read(key, args, "hpttl", "pttl")

    @command_decorator(b"HPERSIST")
    def HPERSIST(self, key: bytes, *args: bytes):
        return self._hexpire_read(key, args, "hpersist", "persist")

    @command_decorator(b"HEXPIRETIME")
    def HEXPIRETIME(self, key: bytes, *args: bytes):
        return self._hexpire_read(key, args, "hexpiretime", "expiretime")

    @command_decorator(b"HPEXPIRETIME")
    def HPEXPIRETIME(self, key: bytes, *args: bytes):
        return self._hexpire_read(key, args, "hpexpiretime", "pexpiretime")
