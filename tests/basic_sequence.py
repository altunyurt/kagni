from kagni.constants import Response

__all__ = ["test_sequence"]

test_sequence = [
    {
        "name": "Check COMMAND return value",
        "command": "COMMAND",
        "args": [],
        "returns": Response.OK,
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
        "args": [b"e", b"1", b"f", b"3424gshm", b"g", "fıstıkçışahap".encode("utf-8")],
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
        "depends": [
            {"command": "SET", "args": [b"k", b"Hello"], "returns": "Response.OK"}
        ],
    },
    {
        "name": "Check DEL return value on non existing keys",
        "command": "DEL",
        "args": [b"e", b"f", b"g", b"nonexistent"],
        "returns": 0,
    },
    ##
    # expire
    ##
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
    ##
    # TTL
    ##
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
        "name": "Check KEYS with no pattern return value",
        "command": "KEYS",
        "args": [],
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
        "expects": lambda cs: cs.data.get(b"b") == b"Hellodeneme",
    },
    {
        "name": "Check SETRANGE return value on existing key offset outside",
        "command": "SETRANGE",
        "args": [b"b", b"50", b"deneme"],
        "returns": 56,
        "depends": [
            {"command": "SET", "args": [b"b", b"Hello World"], "returns": Response.OK}
        ],
        "expects": lambda cs: cs.data.get(b"b")
        == b"Hello World" + b"\x00" * 39 + b"deneme",
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
]
