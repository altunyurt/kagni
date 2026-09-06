from kagni.constants import Response, SimpleString

__all__ = ["test_sequence"]

test_sequence = [
{
            "name": "Check COMMAND returns per-command metadata",
            "command": "COMMAND",
            "args": [],
            "returns": lambda rv, cs: any(
                entry[:2] == [b"GET", 2] and [b"readonly"] in entry
                for entry in rv
                if isinstance(entry, list)
            ),
        },
{
            "name": "Check PING return value",
            "command": "PING",
            "args": [],
            "returns": Response.PONG,
        },
{
            "name": "Check SET return value",
            "command": "SET",
            "args": [b"a", b"1"],
            "returns": Response.OK,
        },
{
            "name": "Check re-SET existing key return value",
            "command": "SET",
            "args": [b"b", b"2"],
            "returns": Response.OK,
            "depends": [{"command": "SET", "args": [b"b", b"1"], "returns": Response.OK}],
        },
{
            "name": "Check SET unicode byte string",
            "command": "SET",
            "args": [b"d", "fıstıkçışahap".encode("utf-8")],
            "returns": Response.OK,
        },
{
            "name": "Check GET return value",
            "command": "GET",
            "args": [b"d"],
            "depends": [{"command": "SET", "args": [b"d", b"10"], "returns": Response.OK}],
            "returns": b"10",
        },
{
            "name": "Check GET nonexisting key return value",
            "command": "GET",
            "args": [b"d"],
            "returns": Response.NIL,
        },
{
            "name": "Check GET return value for unicode encoded string",
            "command": "GET",
            "args": [b"d"],
            "returns": "fıstıkçışahap".encode("utf-8"),
            "depends": [
                {
                    "command": "SET",
                    "args": [b"d", "fıstıkçışahap".encode("utf-8")],
                    "returns": Response.OK,
                }
            ],
        },
{
            "name": "Check GETSET return value",
            "command": "GETSET",
            "args": [b"d", b"20"],
            "depends": [{"command": "SET", "args": [b"d", b"10"], "returns": Response.OK}],
            "returns": b"10",
            "expects": lambda cmds: cmds.data.get(b"d") == b"20",
        },
{
            "name": "Check GETSET nonexisting key return value",
            "command": "GETSET",
            "args": [b"d", b"10"],
            "returns": Response.NIL,
            "expects": lambda cmds: cmds.data.get(b"d") == b"10",
        },
{
            "name": "Check GETSET return value for unicode encoded string",
            "command": "GETSET",
            "args": [b"d", b"foobarz"],
            "returns": "fıstıkçışahap".encode("utf-8"),
            "depends": [
                {
                    "command": "SET",
                    "args": [b"d", "fıstıkçışahap".encode("utf-8")],
                    "returns": Response.OK,
                }
            ],
            "expects": lambda cmds: cmds.data.get(b"d") == b"foobarz",
        },
{
            "name": "Check MSET return value",
            "command": "MSET",
            "args": [
                b"e",
                b"1",
                b"f",
                b"3424gshm",
                b"g",
                "fıstıkçışahap".encode("utf-8"),
            ],
            "returns": Response.OK,
        },
{
            "command": "MGET",
            "args": [b"a", b"b", b"c"],
            "depends": [
                {"command": "SET", "args": [b"a", b"1"], "returns": Response.OK},
                {"command": "SET", "args": [b"b", b"2"], "returns": Response.OK},
                {"command": "SET", "args": [b"c", b"3"], "returns": Response.OK},
                {"command": "SET", "args": [b"d", b"4"], "returns": Response.OK},
            ],
            "returns": [b"1", b"2", b"3"],
        },
{
            "name": "Check DEL return value on existing keys",
            "command": "DEL",
            "args": [b"e", b"f", b"g"],
            "depends": [
                {"command": "SET", "args": [b"e", b"1"], "returns": Response.OK},
                {"command": "SET", "args": [b"f", b"2"], "returns": Response.OK},
                {"command": "SET", "args": [b"g", b"3"], "returns": Response.OK},
                {"command": "SET", "args": [b"d", b"4"], "returns": Response.OK},
            ],
            "returns": 3,
        },
{
            "name": "Check APPEND with non existing key",
            "command": "APPEND",
            "args": [b"k", b"world"],
            "returns": 5,
        },
{
            "name": "Check APPEND with  existing key",
            "command": "APPEND",
            "args": [b"k", b" world"],
            "returns": 11,
            "depends": [{"command": "SET", "args": [b"k", b"Hello"], "returns": "Response.OK"}],
        },
{
            "name": "Check DEL return value on non existing keys",
            "command": "DEL",
            "args": [b"e", b"f", b"g", b"nonexistent"],
            "returns": 0,
        },
{
            "name": "Check expire retval on existing key",
            "command": "EXPIRE",
            "args": [b"e", b"10"],
            "returns": 1,
            "depends": [{"command": "SET", "args": [b"e", b"1"], "returns": Response.OK}],
        },
{
            "name": "Check expire retval on existing key",
            "command": "EXPIRE",
            "args": [b"non-existent", b"10"],
            "returns": 0,
        },
{
            "name": "Check ttl on key",
            "command": "TTL",
            "args": [b"e"],
            "returns": 10,
            "depends": [
                {"command": "SET", "args": [b"e", b"1"], "returns": Response.OK},
                {"command": "EXPIRE", "args": [b"e", b"10"], "returns": Response.OK},
            ],
        },
{
            "name": "Check ttl on key with no expiration",
            "command": "TTL",
            "args": [b"e"],
            "returns": -1,
            "depends": [{"command": "SET", "args": [b"e", b"1"], "returns": Response.OK}],
        },
{
            "name": "Check TTL on expired key",
            "command": "TTL",
            "args": [b"e"],
            "returns": -2,
            "depends": [
                {"command": "SET", "args": [b"e", b"1"], "returns": Response.OK},
                {"command": "EXPIRE", "args": [b"e", b"-10"], "returns": Response.OK},
            ],
        },
{
            "name": "Check TTL on nonexisting key",
            "command": "TTL",
            "args": [b"nonexistent"],
            "returns": -2,
        },
{
            "name": "Check KEYS with glob * pattern return value",
            "command": "KEYS",
            "args": [b"*"],
            "depends": [
                {
                    "command": "MSET",
                    "args": [b"a", b"1", b"b", b"1", b"c", b"1", b"d", b"1", b"e", b"1"],
                    "returns": Response.OK,
                }
            ],
            "returns": [b"a", b"b", b"c", b"d", b"e"],
        },
{
            "name": "Check KEYS with glob pattern return value",
            "command": "KEYS",
            "args": [b"*"],
            "depends": [
                {
                    "command": "MSET",
                    "args": [b"a", b"1", b"b", b"1", b"c", b"1", b"d", b"1", b"e", b"1"],
                    "returns": Response.OK,
                }
            ],
            "returns": [b"a", b"b", b"c", b"d", b"e"],
        },
{
            "name": "Check KEYS with glob * pattern return value",
            "command": "KEYS",
            "args": [b"[ae]*"],
            "depends": [
                {
                    "command": "MSET",
                    "args": [b"a", b"1", b"b", b"1", b"c", b"1", b"d", b"1", b"e", b"1"],
                    "returns": Response.OK,
                }
            ],
            "returns": [b"a", b"e"],
        },
{
            "name": "Check KEYS with glob non-matching pattern return value",
            "command": "KEYS",
            "args": [b"[gf]*"],
            "depends": [
                {
                    "command": "MSET",
                    "args": [b"a", b"1", b"b", b"1", b"c", b"1", b"d", b"1", b"e", b"1"],
                    "returns": Response.OK,
                }
            ],
            "returns": [],
        },
{
            "name": "Check INCR return value ",
            "command": "INCR",
            "args": [b"b"],
            "depends": [{"command": "SET", "args": [b"b", b"1"], "returns": Response.OK}],
            "returns": 2,
        },
{
            "name": "Check INCR return value on nonexisting key",
            "command": "INCR",
            "args": [b"c"],
            "returns": 1,
        },
{
            "name": "Check INCRBY return value ",
            "command": "INCRBY",
            "args": [b"b", b"18"],
            "depends": [{"command": "SET", "args": [b"b", b"75"], "returns": Response.OK}],
            "returns": 93,
        },
{
            "name": "Check INCRBY return value on nonexisting key",
            "command": "INCRBY",
            "args": [b"c", b"23"],
            "returns": 23,
        },
{
            "name": "Check DECR return value ",
            "command": "DECR",
            "args": [b"b"],
            "depends": [{"command": "SET", "args": [b"b", b"1"], "returns": Response.OK}],
            "returns": 0,
        },
{
            "name": "Check DECR return value on nonexisting key",
            "command": "DECR",
            "args": [b"c"],
            "returns": -1,
        },
{
            "name": "Check DECRBY return value ",
            "command": "DECRBY",
            "args": [b"b", b"18"],
            "depends": [{"command": "SET", "args": [b"b", b"75"], "returns": Response.OK}],
            "returns": 57,
        },
{
            "name": "Check DECRBY return value on nonexisting key",
            "command": "DECRBY",
            "args": [b"c", b"23"],
            "returns": -23,
        },
{
            "name": "Check GETRANGE return value ",
            "command": "GETRANGE",
            "args": [b"b", b"4", b"10"],
            "returns": b"o world",
            "depends": [
                {"command": "SET", "args": [b"b", b"hello world"], "returns": Response.OK}
            ],
        },
{
            "name": "Check GETRANGE return value on nonexisting key ",
            "command": "GETRANGE",
            "args": [b"b", b"4", b"10"],
            "returns": b"",
        },
{
            "name": "Check SETRANGE with nonexisting key",
            "command": "SETRANGE",
            "args": [b"b", b"10", b"Hello"],
            "returns": 15,
            "expects": lambda cs: cs.data.get(b"b") == b"\x00" * 10 + b"Hello",
        },
{
            "name": "Check SETRANGE return value on existing key offset inside",
            "command": "SETRANGE",
            "args": [b"b", b"5", b"deneme"],
            "returns": 11,
            "depends": [
                {"command": "SET", "args": [b"b", b"Hello World"], "returns": Response.OK}
            ],
            "expects": lambda cs: cs.data.get(b"b") == b"Hellodeneme"
        },
{
            "name": "Check SETRANGE return value on existing key offset outside",
            "command": "SETRANGE",
            "args": [b"b", b"50", b"deneme"],
            "returns": 56,
            "depends": [
                {"command": "SET", "args": [b"b", b"Hello World"], "returns": Response.OK}
            ],
            "expects": lambda cs: cs.data.get(b"b") == b"Hello World" + b"\x00" * 39 + b"deneme"
        },
{
            "name": "Check FLUSHDB works",
            "command": "FLUSHDB",
            "args": [],
            "depends": [
                {"command": "SETBIT", "args": [b"b", b"0", b"1"], "returns": 0},
                {"command": "SETBIT", "args": [b"b", b"1", b"1"], "returns": 0},
                {"command": "SETBIT", "args": [b"b", b"2", b"1"], "returns": 0},
                {"command": "SETBIT", "args": [b"b", b"4", b"1"], "returns": 0},
            ],
            "returns": Response.OK,
            "expects": lambda cmds: len(cmds.data) == 0,
        },
{
            "name": "Check FLUSHALL works",
            "command": "FLUSHALL",
            "args": [],
            "depends": [
                {"command": "SETBIT", "args": [b"b", b"0", b"1"], "returns": 0},
                {"command": "SETBIT", "args": [b"b", b"1", b"1"], "returns": 0},
                {"command": "SETBIT", "args": [b"b", b"2", b"1"], "returns": 0},
                {"command": "SETBIT", "args": [b"b", b"4", b"1"], "returns": 0},
            ],
            "returns": Response.OK,
            "expects": lambda cmds: len(cmds.data) == 0,
        },

    ##
    # TYPE
    ##
    {
        "name": "Check TYPE on a missing key",
        "command": "TYPE",
        "args": [b"k"],
        "returns": SimpleString("none"),
    },
    {
        "name": "Check TYPE on a string key",
        "command": "TYPE",
        "args": [b"k"],
        "depends": [{"command": "SET", "args": [b"k", b"v"], "returns": Response.OK}],
        "returns": SimpleString("string"),
    },
    {
        "name": "Check TYPE on a hash key",
        "command": "TYPE",
        "args": [b"k"],
        "depends": [{"command": "HSET", "args": [b"k", b"f", b"v"], "returns": 1}],
        "returns": SimpleString("hash"),
    },
    {
        "name": "Check TYPE on a set key",
        "command": "TYPE",
        "args": [b"k"],
        "depends": [{"command": "SADD", "args": [b"k", b"m"], "returns": 1}],
        "returns": SimpleString("set"),
    },

    ##
    # SET options, SETNX/SETEX/PSETEX, MSETNX, GETDEL, GETEX
    ##
    {
        "name": "Check SET with EX sets a TTL",
        "command": "SET",
        "args": [b"k", b"v", b"EX", b"100"],
        "returns": Response.OK,
        "expects": lambda cs: cs.data.ttl(b"k") > 0,
    },
    {
        "name": "Check SET with KEEPTTL keeps the TTL",
        "command": "SET",
        "args": [b"k", b"v2", b"KEEPTTL"],
        "depends": [{"command": "SET", "args": [b"k", b"v", b"EX", b"100"], "returns": Response.OK}],
        "returns": Response.OK,
        "expects": lambda cs: cs.data.ttl(b"k") > 0,
    },
    {
        "name": "Check plain SET clears an existing TTL",
        "command": "SET",
        "args": [b"k", b"v2"],
        "depends": [{"command": "SET", "args": [b"k", b"v", b"EX", b"100"], "returns": Response.OK}],
        "returns": Response.OK,
        "expects": lambda cs: cs.data.ttl(b"k") == -1,
    },
    {
        "name": "Check SET NX on a missing key",
        "command": "SET",
        "args": [b"k", b"v", b"NX"],
        "returns": Response.OK,
        "expects": lambda cs: cs.data.get(b"k") == b"v",
    },
    {
        "name": "Check SET NX on an existing key returns nil",
        "command": "SET",
        "args": [b"k", b"v2", b"NX"],
        "depends": [{"command": "SET", "args": [b"k", b"v", b"NX"], "returns": Response.OK}],
        "returns": Response.NIL,
        "expects": lambda cs: cs.data.get(b"k") == b"v",
    },
    {
        "name": "Check SET XX on an existing key",
        "command": "SET",
        "args": [b"k", b"v2", b"XX"],
        "depends": [{"command": "SET", "args": [b"k", b"v", b"NX"], "returns": Response.OK}],
        "returns": Response.OK,
        "expects": lambda cs: cs.data.get(b"k") == b"v2",
    },
    {
        "name": "Check SET XX on a missing key returns nil",
        "command": "SET",
        "args": [b"k", b"v", b"XX"],
        "returns": Response.NIL,
        "expects": lambda cs: b"k" not in cs.data,
    },
    {
        "name": "Check SET with GET returns the old value",
        "command": "SET",
        "args": [b"k", b"v2", b"GET"],
        "depends": [{"command": "SET", "args": [b"k", b"v", b"NX"], "returns": Response.OK}],
        "returns": b"v",
        "expects": lambda cs: cs.data.get(b"k") == b"v2",
    },
    {
        "name": "Check SET with GET on a missing key returns nil and sets",
        "command": "SET",
        "args": [b"k", b"v", b"GET"],
        "returns": Response.NIL,
        "expects": lambda cs: cs.data.get(b"k") == b"v",
    },
    {
        "name": "Check SET NX GET on an existing key returns it unchanged",
        "command": "SET",
        "args": [b"k", b"blocked", b"NX", b"GET"],
        "depends": [{"command": "SET", "args": [b"k", b"v", b"NX"], "returns": Response.OK}],
        "returns": b"v",
        "expects": lambda cs: cs.data.get(b"k") == b"v",
    },
    {
        "name": "Check SETNX on a missing key",
        "command": "SETNX",
        "args": [b"k", b"v"],
        "returns": 1,
        "expects": lambda cs: cs.data.get(b"k") == b"v",
    },
    {
        "name": "Check SETNX on an existing key",
        "command": "SETNX",
        "args": [b"k", b"v2"],
        "depends": [{"command": "SETNX", "args": [b"k", b"v"], "returns": 1}],
        "returns": 0,
        "expects": lambda cs: cs.data.get(b"k") == b"v",
    },
    {
        "name": "Check SETEX sets a value with a TTL",
        "command": "SETEX",
        "args": [b"k", b"100", b"v"],
        "returns": Response.OK,
        "expects": lambda cs: cs.data.get(b"k") == b"v" and cs.data.ttl(b"k") > 0,
    },
    {
        "name": "Check PSETEX sets a value with a TTL",
        "command": "PSETEX",
        "args": [b"k", b"100000", b"v"],
        "returns": Response.OK,
        "expects": lambda cs: cs.data.get(b"k") == b"v" and cs.data.ttl(b"k") > 0,
    },
    {
        "name": "Check GETDEL returns the value and removes the key",
        "command": "GETDEL",
        "args": [b"k"],
        "depends": [{"command": "SET", "args": [b"k", b"v"], "returns": Response.OK}],
        "returns": b"v",
        "expects": lambda cs: b"k" not in cs.data,
    },
    {
        "name": "Check GETDEL on a missing key",
        "command": "GETDEL",
        "args": [b"k"],
        "returns": Response.NIL,
    },
    {
        "name": "Check GETEX returns the value",
        "command": "GETEX",
        "args": [b"k"],
        "depends": [{"command": "SET", "args": [b"k", b"v"], "returns": Response.OK}],
        "returns": b"v",
    },
    {
        "name": "Check GETEX on a missing key",
        "command": "GETEX",
        "args": [b"k"],
        "returns": Response.NIL,
    },
    {
        "name": "Check GETEX with EX sets a TTL",
        "command": "GETEX",
        "args": [b"k", b"EX", b"100"],
        "depends": [{"command": "SET", "args": [b"k", b"v"], "returns": Response.OK}],
        "returns": b"v",
        "expects": lambda cs: cs.data.ttl(b"k") > 0,
    },
    {
        "name": "Check GETEX with PERSIST clears the TTL",
        "command": "GETEX",
        "args": [b"k", b"PERSIST"],
        "depends": [
            {"command": "SET", "args": [b"k", b"v", b"EX", b"100"], "returns": Response.OK}
        ],
        "returns": b"v",
        "expects": lambda cs: cs.data.ttl(b"k") == -1,
    },
    {
        "name": "Check MSETNX sets all keys when none exist",
        "command": "MSETNX",
        "args": [b"a", b"1", b"b", b"2"],
        "returns": 1,
        "expects": lambda cs: cs.data.get(b"a") == b"1" and cs.data.get(b"b") == b"2",
    },
    {
        "name": "Check MSETNX sets nothing when a key exists",
        "command": "MSETNX",
        "args": [b"a", b"9", b"c", b"3"],
        "depends": [{"command": "MSETNX", "args": [b"a", b"1", b"b", b"2"], "returns": 1}],
        "returns": 0,
        "expects": lambda cs: cs.data.get(b"a") == b"1" and cs.data.get(b"c") is None,
    },
    ##
    # EXISTS / TOUCH / DBSIZE
    ##
    {
        "name": "Check EXISTS counts existing keys",
        "command": "EXISTS",
        "args": [b"a", b"b", b"nope"],
        "depends": [
            {"command": "SET", "args": [b"a", b"1"], "returns": Response.OK},
            {"command": "SET", "args": [b"b", b"2"], "returns": Response.OK},
        ],
        "returns": 2,
    },
    {
        "name": "Check EXISTS on missing keys",
        "command": "EXISTS",
        "args": [b"nope"],
        "returns": 0,
    },
    {
        "name": "Check TOUCH counts existing keys",
        "command": "TOUCH",
        "args": [b"a", b"nope"],
        "depends": [{"command": "SET", "args": [b"a", b"1"], "returns": Response.OK}],
        "returns": 1,
    },
    {
        "name": "Check DBSIZE",
        "command": "DBSIZE",
        "args": [],
        "depends": [
            {"command": "SET", "args": [b"a", b"1"], "returns": Response.OK},
            {"command": "SET", "args": [b"b", b"2"], "returns": Response.OK},
        ],
        "returns": 2,
    },

    ##
    # INCRBYFLOAT / SCAN / CLIENT
    ##
    {
        "name": "Check INCRBYFLOAT on a missing key starts from zero",
        "command": "INCRBYFLOAT",
        "args": [b"f", b"10.5"],
        "returns": b"10.5",
        "expects": lambda cs: cs.data.get(b"f") == b"10.5",
    },
    {
        "name": "Check INCRBYFLOAT subtracts back to an integer",
        "command": "INCRBYFLOAT",
        "args": [b"f", b"-10.5"],
        "depends": [
            {"command": "INCRBYFLOAT", "args": [b"f", b"10.5"], "returns": b"10.5"}
        ],
        "returns": b"0",
    },
    {
        "name": "Check INCRBYFLOAT float precision",
        "command": "INCRBYFLOAT",
        "args": [b"f", b"0.2"],
        "depends": [{"command": "SET", "args": [b"f", b"0.1"], "returns": Response.OK}],
        "returns": b"0.30000000000000004",
    },
    {
        "name": "Check INCRBYFLOAT on an integer string",
        "command": "INCRBYFLOAT",
        "args": [b"f", b"0.5"],
        "depends": [{"command": "SET", "args": [b"f", b"10"], "returns": Response.OK}],
        "returns": b"10.5",
    },
    {
        "name": "Check SCAN returns the whole snapshot in one step",
        "command": "SCAN",
        "args": [b"0"],
        "depends": [
            {"command": "SET", "args": [b"a", b"1"], "returns": Response.OK},
            {"command": "SET", "args": [b"b", b"2"], "returns": Response.OK},
        ],
        "returns": [b"0", [b"a", b"b"]],
    },
    {
        "name": "Check SCAN on an empty keyspace",
        "command": "SCAN",
        "args": [b"0"],
        "returns": [b"0", []],
    },
    {
        "name": "Check SCAN with MATCH",
        "command": "SCAN",
        "args": [b"0", b"MATCH", b"a*"],
        "depends": [
            {"command": "SET", "args": [b"a1", b"1"], "returns": Response.OK},
            {"command": "SET", "args": [b"b1", b"2"], "returns": Response.OK},
        ],
        "returns": [b"0", [b"a1"]],
    },
    {
        "name": "Check SCAN with TYPE filter",
        "command": "SCAN",
        "args": [b"0", b"TYPE", b"hash"],
        "depends": [
            {"command": "SET", "args": [b"str", b"1"], "returns": Response.OK},
            {"command": "HSET", "args": [b"hsh", b"f", b"v"], "returns": 1},
        ],
        "returns": [b"0", [b"hsh"]],
    },
    {
        "name": "Check CLIENT SETINFO is accepted",
        "command": "CLIENT",
        "args": [b"SETINFO", b"lib-name", b"redis-py"],
        "returns": Response.OK,
    },
    {
        "name": "Check CLIENT SETNAME is accepted",
        "command": "CLIENT",
        "args": [b"SETNAME", b"conn-1"],
        "returns": Response.OK,
    },
    {
        "name": "Check CLIENT GETNAME returns an empty bulk",
        "command": "CLIENT",
        "args": [b"GETNAME"],
        "returns": b"",
    },
    {
        "name": "Check CLIENT ID",
        "command": "CLIENT",
        "args": [b"ID"],
        "returns": 1,
    },
]
