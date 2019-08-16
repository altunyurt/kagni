from kagni.constants import Response

__all__ = ["test_sequence"]

test_sequence = [
    {
        "name": "Check HSET return value for nonexisting key",
        "command": "HSET",
        "args": [b"k", b"f", b"123"],
        "returns": 1,
        "expects": lambda cmds: cmds.data[b"k"][b"f"] == b"123",
    },
    {
        "name": "Check HSET return value for existing key",
        "command": "HSET",
        "args": [b"k", b"f", b"foobarz"],
        "returns": 0,
        "depends": [{"command": "HSET", "args": [b"k", b"f", b"123"], "returns": 1}],
        "expects": lambda cmds: cmds.data[b"k"][b"f"] == b"foobarz",
    },
    {
        "name": "Check HGET return value for nonexisting key",
        "command": "HGET",
        "args": [b"k", b"f"],
        "returns": Response.NIL,
    },
    {
        "name": "Check HGET return value for nonexisting field",
        "command": "HGET",
        "args": [b"k", b"f"],
        "returns": Response.NIL,
        "depends": [
            {"command": "HSET", "args": [b"k", b"another_f", b"123"], "returns": 1}
        ],
    },
    {
        "name": "Check HGET return value for existing key",
        "command": "HGET",
        "args": [b"k", b"f"],
        "returns": b"foobarz",
        "depends": [{"command": "HSET", "args": [b"k", b"f", b"foobarz"], "returns": 1}],
    },
    {
        "name": "Check HEXISTS return value for nonexisting key",
        "command": "HEXISTS",
        "args": [b"k", b"f"],
        "returns": 0,
    },
    {
        "name": "Check HEXISTS return value for nonexisting field",
        "command": "HEXISTS",
        "args": [b"k", b"f"],
        "returns": 0,
        "depends": [
            {"command": "HSET", "args": [b"k", b"another_f", b"123"], "returns": 1}
        ],
    },
    {
        "name": "Check HEXISTS return value for existing field",
        "command": "HEXISTS",
        "args": [b"k", b"f"],
        "returns": 1,
        "depends": [{"command": "HSET", "args": [b"k", b"f", b"123"], "returns": 1}],
    },
    {
        "name": "Check HDEL return value for non existing key",
        "command": "HDEL",
        "args": [b"k", b"f"],
        "returns": 0,
    },
    {
        "name": "Check HDEL return value for non existing fields",
        "command": "HDEL",
        "args": [b"k", b"f", b"z", b"a"],
        "returns": 0,
        "depends": [
            {"command": "HSET", "args": [b"k", b"other_key", b"123"], "returns": 1}
        ],
    },
    {
        "name": "Check HDEL return value for some existing and some not keys",
        "command": "HDEL",
        "args": [b"k", b"f", b"z", b"a", b"c"],
        "returns": 3,
        "depends": [
            {"command": "HSET", "args": [b"k", b"f", b"123"], "returns": 1},
            {"command": "HSET", "args": [b"k", b"a", b"123"], "returns": 1},
            {"command": "HSET", "args": [b"k", b"other_key", b"123"], "returns": 1},
            {"command": "HSET", "args": [b"k", b"c", b"123"], "returns": 1},
        ],
    },
    {
        "name": "Check HGETALL for nonexisting key",
        "command": "HGETALL",
        "args": [b"k"],
        "returns": [],
    },
    {
        "name": "Check HGETALL for existing key with no fields ",
        "command": "HGETALL",
        "args": [b"k"],
        "returns": [],
        "depends": [
            {"command": "HSET", "args": [b"k", b"f", b"123"], "returns": 1},
            {"command": "HDEL", "args": [b"k", b"f"], "returns": 1},
        ],
    },
    {
        "name": "Check HGETALL return value for existing key and fields",
        "command": "HGETALL",
        "args": [b"k"],
        "returns": [b"f", b"123", b"a", b"234", b"other_key", b"345", b"c", b"456"],
        "depends": [
            {"command": "HSET", "args": [b"k", b"f", b"123"], "returns": 1},
            {"command": "HSET", "args": [b"k", b"a", b"234"], "returns": 1},
            {"command": "HSET", "args": [b"k", b"other_key", b"345"], "returns": 1},
            {"command": "HSET", "args": [b"k", b"c", b"456"], "returns": 1},
        ],
    },
]
