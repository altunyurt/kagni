from typing import List
import fnmatch
import math
import os
import platform
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
    KIND_ZSET,
    RE_NUMERIC,
    _format_float,
    _parse_float,
    expect_kind,
    kind_of,
    string2ll,
)
from .decorator import command_decorator


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
    KIND_ZSET: "zset",
    KIND_BITMAP: "string",
}


# commands that write the keyspace (everything else with keys is
# classified read-only below; connection/server commands carry no
# write flag)
_WRITE_COMMANDS = frozenset(
    b"append decr decrby del expire expireat getdel getex getset incr "
    b"incrby incrbyfloat mset msetnx persist pexpire pexpireat psetex set "
    b"setex setnx setrange setbit bitop "
    b"linsert lmove lmpop lpop lpush lpushx lrem lset ltrim rpop rpoplpush "
    b"rpush rpushx "
    b"sadd sdiffstore sinterstore smove spop srem sunionstore "
    b"hdel hincrby hset "
    b"zadd zdiffstore zincrby zinterstore zpopmax zpopmin zrem "
    b"zremrangebylex zremrangebyrank zremrangebyscore zunionstore "
    b"flushall flushdb".split()
)
# read-only commands never modify the keyspace; the rest (PING, CLIENT,
# MULTI, ...) carry no flag at all, like redis' non-readonly flags
_READONLY_COMMANDS = frozenset(
    b"get mget strlen getrange exists type ttl pttl keys scan dbsize touch "
    b"echo config info command "
    b"getbit bitcount bitpos "
    b"llen lindex lrange lpos "
    b"scard sdiff sinter sismember smembers srandmember sunion "
    b"hget hmget hexists hlen hkeys hvals hgetall "
    b"zcard zcount zdiff zinter zlexcount zmscore zrandmember zrange "
    b"zrangebylex zrangebyscore zrank zrevrange zrevrangebylex "
    b"zrevrangebyscore zrevrank zscore zunion".split()
)
_ADMIN_COMMANDS = frozenset(b"flushall flushdb config".split())

# redis' help groups for COMMAND DOCS output
_COMMAND_GROUPS = {
    b"get": "string", b"mget": "string", b"strlen": "string",
    b"getrange": "string", b"getset": "string", b"getdel": "string",
    b"getex": "string", b"set": "string", b"setnx": "string",
    b"setex": "string", b"psetex": "string", b"mset": "string",
    b"msetnx": "string", b"append": "string", b"incr": "string",
    b"decr": "string", b"incrby": "string", b"decrby": "string",
    b"incrbyfloat": "string", b"setrange": "string", b"echo": "connection",
    b"ping": "connection", b"client": "connection",
    b"setbit": "bitmap", b"getbit": "bitmap", b"bitcount": "bitmap",
    b"bitpos": "bitmap", b"bitop": "bitmap",
    b"lpush": "list", b"rpush": "list", b"lpushx": "list",
    b"rpushx": "list", b"llen": "list", b"lindex": "list",
    b"lset": "list", b"lrange": "list", b"ltrim": "list",
    b"lrem": "list", b"linsert": "list", b"lpop": "list",
    b"rpop": "list", b"lmove": "list", b"rpoplpush": "list",
    b"lpos": "list", b"lmpop": "list",
    b"sadd": "set", b"scard": "set", b"smembers": "set",
    b"sismember": "set", b"srem": "set", b"spop": "set",
    b"srandmember": "set", b"smove": "set", b"sdiff": "set",
    b"sdiffstore": "set", b"sinter": "set", b"sinterstore": "set",
    b"sunion": "set", b"sunionstore": "set",
    b"hset": "hash", b"hget": "hash", b"hmget": "hash",
    b"hexists": "hash", b"hdel": "hash", b"hlen": "hash",
    b"hkeys": "hash", b"hvals": "hash", b"hgetall": "hash",
    b"hincrby": "hash",
    b"zadd": "sorted-set", b"zcard": "sorted-set",
    b"zscore": "sorted-set", b"zmscore": "sorted-set",
    b"zincrby": "sorted-set", b"zrank": "sorted-set",
    b"zrevrank": "sorted-set", b"zrange": "sorted-set",
    b"zrevrange": "sorted-set", b"zrangebyscore": "sorted-set",
    b"zrevrangebyscore": "sorted-set", b"zrangebylex": "sorted-set",
    b"zrevrangebylex": "sorted-set", b"zcount": "sorted-set",
    b"zlexcount": "sorted-set", b"zrem": "sorted-set",
    b"zremrangebyrank": "sorted-set", b"zremrangebyscore": "sorted-set",
    b"zremrangebylex": "sorted-set", b"zpopmin": "sorted-set",
    b"zpopmax": "sorted-set", b"zrandmember": "sorted-set",
    b"zunionstore": "sorted-set", b"zinterstore": "sorted-set",
    b"zdiffstore": "sorted-set", b"zunion": "sorted-set",
    b"zinter": "sorted-set", b"zdiff": "sorted-set",
    b"del": "generic", b"expire": "generic", b"pexpire": "generic",
    b"expireat": "generic", b"pexpireat": "generic", b"persist": "generic",
    b"ttl": "generic", b"pttl": "generic", b"type": "generic",
    b"keys": "generic", b"scan": "generic", b"exists": "generic",
    b"touch": "generic", b"dbsize": "generic", b"flushdb": "server",
    b"flushall": "server", b"command": "server", b"config": "server",
    b"info": "server",
}


def _command_table(cls):
    """{NAME: (arity, flags, group)} for every registered command.

    Arity follows the redis convention (the command word included):
    exact counts are positive, variable commands negative.  Redis-6-era
    entry shape on purpose (name/arity/flags/first/last/step)."""
    table = {}
    for klass in cls.__mro__:
        for attr in vars(klass).values():
            name = getattr(attr, "command_name", None)
            if name is None:
                continue
            if attr.max_args is not None and attr.max_args == attr.min_args:
                arity = attr.max_args + 1
            else:
                arity = -(attr.min_args + 1)
            flags = []
            lower = name.lower()
            if lower in _WRITE_COMMANDS:
                flags.append(b"write")
            elif lower in _READONLY_COMMANDS:
                flags.append(b"readonly")
            if lower in _ADMIN_COMMANDS:
                flags.append(b"admin")
            table[name] = (arity, flags, _COMMAND_GROUPS.get(lower, "generic"))
    return table


# --------------------------------------------------------------- INFO
# the sections INFO knows about; unknown section names reply with an
# empty body (redis behaviour), and the defaults cover everything kagni
# has
_INFO_SECTIONS = (b"server", b"keyspace")


def _info_body(sections, data, port):
    """INFO reply body: '# Section' blocks with redis' key:value lines.
    Values describe kagni honestly; redis_version reports the 7.4
    compatibility target so clients gate their features on it."""
    wanted = set()
    for section in sections:
        section = section.lower()
        if section in (b"all", b"default", b"everything") or not section:
            wanted.update(_INFO_SECTIONS)
        elif section in _INFO_SECTIONS:
            wanted.add(section)
    # an unknown section name is not an error: it simply matches nothing
    blocks = []
    if b"server" in wanted:
        blocks.append(
            "# Server\r\n"
            "redis_version:7.4.0\r\n"
            "redis_git_sha1:00000000\r\n"
            "redis_git_dirty:0\r\n"
            "redis_build_id:0000000000000000\r\n"
            "redis_mode:standalone\r\n"
            "os:%s %s\r\n"
            "arch_bits:64\r\n"
            "process_id:%d\r\n"
            "tcp_port:%d\r\n"
            "uptime_in_seconds:%d\r\n"
            % (
                platform.system(),
                platform.machine(),
                os.getpid(),
                port,
                int(_wall.monotonic()),
            )
        )
    if b"keyspace" in wanted:
        keys, expires, avg_ttl = data.keyspace_stats()
        block = "# Keyspace\r\n"
        if keys:
            block += "db0:keys=%d,expires=%d,avg_ttl=%d\r\n" % (
                keys,
                expires,
                avg_ttl,
            )
        blocks.append(block)
    return b"\r\n".join(block.encode() for block in blocks)



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

    @command_decorator(b"ECHO")
    def ECHO(self, message: bytes) -> bytes:
        return message

    @command_decorator(b"COMMAND")
    def COMMAND(self, *args: bytes):
        """COMMAND | COUNT | DOCS [name ...]: per-command metadata in
        redis' shapes (name/arity/flags triples, a count, or the docs
        map), so clients that enumerate the server surface get arrays
        instead of the old +OK stub.  Arity follows the decorator's
        min/max (the redis convention: exact counts positive, variable
        commands negative); flags carry write/readonly/admin."""
        if not args:
            entries = []
            for name, (arity, flags, group) in _command_table(type(self)).items():
                entries.append([name, arity, flags, 0, 0, 0])
            return entries
        sub = args[0].upper()
        if sub == b"COUNT" and len(args) == 1:
            return len(_command_table(type(self)))
        if sub == b"DOCS":
            table = _command_table(type(self))
            if len(args) == 1:
                wanted = sorted(table)
            else:
                wanted = [a.upper() for a in args[1:]]
            docs = []
            for name in wanted:
                if name not in table:
                    continue  # unknown names are skipped, like redis
                arity, flags, group = table[name]
                docs.append(
                    [
                        name,
                        [
                            b"summary",
                            b"",
                            b"since",
                            b"0.9.0",
                            b"group",
                            group.encode(),
                            b"arity",
                            arity,
                            b"flags",
                            flags,
                        ],
                    ]
                )
            return docs
        name = sub.decode("ascii", "replace")
        raise Error(
            "ERR",
            "Unknown subcommand or wrong number of arguments for '{}'. "
            "Try COMMAND HELP.".format(name),
        )

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

    @command_decorator(b"INFO")
    def INFO(self, *sections: bytes) -> bytes:
        """INFO [section ...]: server and keyspace sections (all that
        kagni tracks), in redis' '# Section' block format.  Unknown
        section names reply with an empty body, like redis."""
        return _info_body(sections or (b"default",), self.data, self.tcp_port)

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

    @command_decorator(b"PEXPIRE")
    def PEXPIRE(self, key: bytes, ms: int) -> int:
        return self.data.expire_at(key, _wall.time_ns() + ms * 1_000_000)

    @command_decorator(b"EXPIREAT")
    def EXPIREAT(self, key: bytes, ts: int) -> int:
        return self.data.expire_at(key, ts * 1_000_000_000)

    @command_decorator(b"PEXPIREAT")
    def PEXPIREAT(self, key: bytes, ts: int) -> int:
        return self.data.expire_at(key, ts * 1_000_000)

    @command_decorator(b"PERSIST")
    def PERSIST(self, key: bytes) -> int:
        return self.data.persist(key)

    @command_decorator(b"TTL")
    def TTL(self, key: bytes) -> int:
        return self.data.ttl(key)

    @command_decorator(b"PTTL")
    def PTTL(self, key: bytes) -> int:
        return self.data.ttl_ms(key)

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
