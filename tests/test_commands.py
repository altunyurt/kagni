from kagni.commands import Commands
from kagni.data import Data
from kagni.constants import COMMAND
from kagni.constants import NIL
from kagni.constants import OK
from kagni.constants import PONG
from kagni.constants import QUEUED
from kagni.resp import protocolBuilder
from kagni.resp import protocolParser
from random import choice
from string import ascii_letters
from string import hexdigits
import pytest


def test_commands():
    test_sequence = [
        {
            "name": "Check COMMAND return value",
            "command": "COMMAND",
            "args": [],
            "returns": OK,
        },
        {
            "name": "Check PING return value",
            "command": "PING",
            "args": [],
            "returns": PONG,
        },
        {
            "name": "Check SET return value",
            "command": "SET",
            "args": [b"a", b"1"],
            "returns": OK,
        },
        {
            "name": "Check re-SET existing key return value",
            "command": "SET",
            "args": [b"b", b"2"],
            "returns": OK,
            "depends": [{"command": "SET", "args": [b"b", b"1"], "returns": OK}],
        },
        {
            "name": "Check SET unicode byte string",
            "command": "SET",
            "args": [b"d", "fıstıkçışahap".encode("utf-8")],
            "returns": OK,
        },
        {
            "name": "Check GET return value",
            "command": "GET",
            "args": [b"d"],
            "depends": [{"command": "SET", "args": [b"d", b"10"], "returns": OK}],
            "returns": b"10",
        },
        {
            "name": "Check GET nonexisting key return value",
            "command": "GET",
            "args": [b"d"],
            "returns": NIL,
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
                    "returns": OK,
                }
            ],
        },
        {
            "name": "Check GETSET return value",
            "command": "GETSET",
            "args": [b"d", b"20"],
            "depends": [{"command": "SET", "args": [b"d", b"10"], "returns": OK}],
            "returns": b"10",
            "expects": lambda cmds: cmds.data.get(b"d") == b"20",
        },
        {
            "name": "Check GETSET nonexisting key return value",
            "command": "GETSET",
            "args": [b"d", b"10"],
            "returns": NIL,
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
                    "returns": OK,
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
            "returns": OK,
        },
        {
            "command": "MGET",
            "args": [b"a", b"b", b"c"],
            "depends": [
                {"command": "SET", "args": [b"a", b"1"], "returns": OK},
                {"command": "SET", "args": [b"b", b"2"], "returns": OK},
                {"command": "SET", "args": [b"c", b"3"], "returns": OK},
                {"command": "SET", "args": [b"d", b"4"], "returns": OK},
            ],
            "returns": [b"1", b"2", b"3"],
        },
        {
            "name": "Check DEL return value on existing keys",
            "command": "DEL",
            "args": [b"e", b"f", b"g"],
            "depends": [
                {"command": "SET", "args": [b"e", b"1"], "returns": OK},
                {"command": "SET", "args": [b"f", b"2"], "returns": OK},
                {"command": "SET", "args": [b"g", b"3"], "returns": OK},
                {"command": "SET", "args": [b"d", b"4"], "returns": OK},
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
            "depends": [{"command": "SET", "args": [b"k", b"Hello"], "returns": "OK"}],
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
            "depends": [{"command": "SET", "args": [b"e", b"1"], "returns": OK}],
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
                {"command": "SET", "args": [b"e", b"1"], "returns": OK},
                {"command": "EXPIRE", "args": [b"e", b"10"], "returns": OK},
            ],
        },
        {
            "name": "Check ttl on key with no expiration",
            "command": "TTL",
            "args": [b"e"],
            "returns": -1,
            "depends": [{"command": "SET", "args": [b"e", b"1"], "returns": OK}],
        },
        {
            "name": "Check TTL on expired key",
            "command": "TTL",
            "args": [b"e"],
            "returns": -2,
            "depends": [
                {"command": "SET", "args": [b"e", b"1"], "returns": OK},
                {"command": "EXPIRE", "args": [b"e", b"-10"], "returns": OK},
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
                    "returns": OK,
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
                    "returns": OK,
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
                    "returns": OK,
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
                    "returns": OK,
                }
            ],
            "returns": [],
        },
        {
            "name": "Check INCR return value ",
            "command": "INCR",
            "args": [b"b"],
            "depends": [{"command": "SET", "args": [b"b", b"1"], "returns": OK}],
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
            "depends": [{"command": "SET", "args": [b"b", b"75"], "returns": OK}],
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
            "depends": [{"command": "SET", "args": [b"b", b"1"], "returns": OK}],
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
            "depends": [{"command": "SET", "args": [b"b", b"75"], "returns": OK}],
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
                {"command": "SET", "args": [b"b", b"hello world"], "returns": OK}
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
                {"command": "SET", "args": [b"b", b"Hello World"], "returns": OK}
            ],
            "expects": lambda cs: cs.data.get(b"b") == b"Hellodeneme"
        },
        {
            "name": "Check SETRANGE return value on existing key offset outside",
            "command": "SETRANGE",
            "args": [b"b", b"50", b"deneme"],
            "returns": 56,
            "depends": [
                {"command": "SET", "args": [b"b", b"Hello World"], "returns": OK}
            ],
            "expects": lambda cs: cs.data.get(b"b") == b"Hello World" + b"\x00" * 39 + b"deneme"
        },
        ##
        # BITOPS
        ##
        {
            "name": "Check SETBIT return value on non existing key",
            "command": "SETBIT",
            "args": [b"b", b"1", b"1"],
            "returns": 0,
        },
        {
            "name": "Check SETBIT return value on existing key",
            "command": "SETBIT",
            "args": [b"b", b"1", b"0"],
            "returns": 1,
            "depends": [{"command": "SETBIT", "args": [b"b", b"1", b"1"], "returns": 0}],
        },
        {
            "name": "Check GETBIT return value on non existing key",
            "command": "GETBIT",
            "args": [b"b", b"1"],
            "returns": 0,
        },
        {
            "name": "Check GETBIT return value on key",
            "command": "GETBIT",
            "args": [b"b", b"1"],
            "returns": 1,
            "depends": [{"command": "SETBIT", "args": [b"b", b"1", b"1"], "returns": 0}],
        },
        {
            "name": "Check GETBIT return value on key non existing bit",
            "command": "GETBIT",
            "args": [b"b", b"100"],
            "returns": 0,
            "depends": [{"command": "SETBIT", "args": [b"b", b"2", b"1"], "returns": 0}],
        },
        {
            "name": "Check BITOP return value for AND",
            "command": "BITOP",
            "args": [b"and", b"target", b"b", b"c", b"d"],
            "returns": 7,
            "depends": [
                {"command": "SETBIT", "args": [b"b", b"10", b"1"], "returns": 0},
                {"command": "SETBIT", "args": [b"b", b"20", b"1"], "returns": 0},
                {"command": "SETBIT", "args": [b"b", b"30", b"1"], "returns": 0},
                {"command": "SETBIT", "args": [b"c", b"20", b"1"], "returns": 0},
                {"command": "SETBIT", "args": [b"c", b"30", b"1"], "returns": 0},
                {"command": "SETBIT", "args": [b"c", b"40", b"1"], "returns": 0},
                {"command": "SETBIT", "args": [b"d", b"30", b"1"], "returns": 0},
                {"command": "SETBIT", "args": [b"d", b"40", b"1"], "returns": 0},
                {"command": "SETBIT", "args": [b"d", b"50", b"1"], "returns": 0},
            ],
        },
        {
            "name": "Check BITOP return value for OR",
            "command": "BITOP",
            "args": [b"or", b"target", b"b", b"c", b"d"],
            "returns": 7,
            "depends": [
                {"command": "SETBIT", "args": [b"b", b"10", b"1"], "returns": 0},
                {"command": "SETBIT", "args": [b"b", b"20", b"1"], "returns": 0},
                {"command": "SETBIT", "args": [b"b", b"30", b"1"], "returns": 0},
                {"command": "SETBIT", "args": [b"c", b"20", b"1"], "returns": 0},
                {"command": "SETBIT", "args": [b"c", b"30", b"1"], "returns": 0},
                {"command": "SETBIT", "args": [b"c", b"40", b"1"], "returns": 0},
                {"command": "SETBIT", "args": [b"d", b"30", b"1"], "returns": 0},
                {"command": "SETBIT", "args": [b"d", b"40", b"1"], "returns": 0},
                {"command": "SETBIT", "args": [b"d", b"50", b"1"], "returns": 0},
            ],
        },
        {
            "name": "Check BITOP return value for XOR",
            "command": "BITOP",
            "args": [b"xor", b"target", b"b", b"c", b"d"],
            "returns": 7,
            "depends": [
                {"command": "SETBIT", "args": [b"b", b"10", b"1"], "returns": 0},
                {"command": "SETBIT", "args": [b"b", b"20", b"1"], "returns": 0},
                {"command": "SETBIT", "args": [b"b", b"30", b"1"], "returns": 0},
                {"command": "SETBIT", "args": [b"c", b"20", b"1"], "returns": 0},
                {"command": "SETBIT", "args": [b"c", b"30", b"1"], "returns": 0},
                {"command": "SETBIT", "args": [b"c", b"40", b"1"], "returns": 0},
                {"command": "SETBIT", "args": [b"d", b"30", b"1"], "returns": 0},
                {"command": "SETBIT", "args": [b"d", b"40", b"1"], "returns": 0},
                {"command": "SETBIT", "args": [b"d", b"50", b"1"], "returns": 0},
            ],
        },
        {
            "name": "Check BITOP return value for NOT",
            "command": "BITOP",
            "args": [b"not", b"target", b"c"],
            "returns": 4,
            "depends": [
                {"command": "SETBIT", "args": [b"c", b"10", b"1"], "returns": 0},
                {"command": "SETBIT", "args": [b"c", b"20", b"1"], "returns": 0},
                {"command": "SETBIT", "args": [b"c", b"30", b"1"], "returns": 0},
            ],
        },
        {
            "name": "Check BITCOUNT return value ",
            "command": "BITCOUNT",
            "args": [b"b"],
            "returns": 6,
            "depends": [
                {"command": "SETBIT", "args": [b"b", b"10", b"1"], "returns": 0},
                {"command": "SETBIT", "args": [b"b", b"20", b"1"], "returns": 0},
                {"command": "SETBIT", "args": [b"b", b"30", b"1"], "returns": 0},
                {"command": "SETBIT", "args": [b"b", b"301", b"1"], "returns": 0},
                {"command": "SETBIT", "args": [b"b", b"3000", b"1"], "returns": 0},
                {"command": "SETBIT", "args": [b"b", b"300000", b"1"], "returns": 0},
            ],
        },
        {
            "name": "Check BITCOUNT return value for nonexisting key",
            "command": "BITCOUNT",
            "args": [b"b"],
            "returns": 0,
        },
        {
            "name": "Check BITPOS 1 return value for existing key",
            "command": "BITPOS",
            "args": [b"b", b"1"],
            "returns": 10,
            "depends": [
                {"command": "SETBIT", "args": [b"b", b"10", b"1"], "returns": 0},
                {"command": "SETBIT", "args": [b"b", b"20", b"1"], "returns": 0},
                {"command": "SETBIT", "args": [b"b", b"30", b"1"], "returns": 0},
            ],
        },
        {
            "name": "Check BITPOS 0 return value for existing key",
            "command": "BITPOS",
            "args": [b"b", b"0"],
            "returns": 3,
            "depends": [
                {"command": "SETBIT", "args": [b"b", b"0", b"1"], "returns": 0},
                {"command": "SETBIT", "args": [b"b", b"1", b"1"], "returns": 0},
                {"command": "SETBIT", "args": [b"b", b"2", b"1"], "returns": 0},
                {"command": "SETBIT", "args": [b"b", b"4", b"1"], "returns": 0},
            ],
        },
        {
            "name": "Check BITPOS  return value for non existing key",
            "command": "BITPOS",
            "args": [b"b", b"0"],
            "returns": -1,
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
            "returns": OK,
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
            "returns": OK,
            "expects": lambda cmds: len(cmds.data) == 0,
        },
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
            "returns": NIL,
        },
        {
            "name": "Check HGET return value for nonexisting field",
            "command": "HGET",
            "args": [b"k", b"f"],
            "returns": NIL,
            "depends": [
                {"command": "HSET", "args": [b"k", b"another_f", b"123"], "returns": 1}
            ],
        },
        {
            "name": "Check HGET return value for existing key",
            "command": "HGET",
            "args": [b"k", b"f"],
            "returns": b"foobarz",
            "depends": [
                {"command": "HSET", "args": [b"k", b"f", b"foobarz"], "returns": 1}
            ],
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
        {
            "name": "Check SADD return value for nonexisting key",
            "command": "SADD",
            "args": [b"k", b"1", b"a", b"3", b"7"],
            "returns": 4,
        },
        {
            "name": "Check SADD return value for existing key",
            "command": "SADD",
            "args": [b"k", b"2", b"b", b"5", b"6"],
            "returns": 4,
            "depends": [
                {"command": "SADD", "args": [b"k", b"1", b"a", b"3", b"7"], "returns": 4}
            ],
        },
        {
            "name": "Check SADD return value for existing key and conflicting values",
            "command": "SADD",
            "args": [b"k", b"1", b"b", b"3", b"6"],
            "returns": 2,
            "depends": [
                {"command": "SADD", "args": [b"k", b"1", b"a", b"3", b"7"], "returns": 4}
            ],
        },
        {
            "name": "Check SCARD return value for nonexisting key",
            "command": "SCARD",
            "args": [b"k"],
            "returns": 0,
        },
        {
            "name": "Check SCARD return value for existing key",
            "command": "SCARD",
            "args": [b"k"],
            "returns": 4,
            "depends": [
                {"command": "SADD", "args": [b"k", b"1", b"a", b"3", b"7"], "returns": 4}
            ],
        },
        {
            "name": "Check SMEMBERS return value for existing key",
            "command": "SMEMBERS",
            "args": [b"k"],
            "returns": [],
        },
        {
            "name": "Check SMEMBERS return value for existing key",
            "command": "SMEMBERS",
            "args": [b"k"],
            "returns": list(set([b"1", b"a", b"3", b"7"])),
            "depends": [
                {"command": "SADD", "args": [b"k", b"1", b"a", b"3", b"7"], "returns": 4}
            ],
        },
        {
            "name": "Check SREM return value for existing key",
            "command": "SREM",
            "args": [b"k", b"a"],
            "returns": 0,
        },
        {
            "name": "Check SREM return value for existing key",
            "command": "SREM",
            "args": [b"k", b"1", b"2", b"hm", b"3", b"rn", b"78"],
            "returns": 3,
            "depends": [
                {
                    "command": "SADD",
                    "args": [b"k", b"1", b"2", b"3", b"4", b"5", b"6", b"7", b"8", b"9"],
                    "returns": 4,
                }
            ],
        },
        {
            "name": "Check SDIFF value for non existing key",
            "command": "SDIFF",
            "args": [b"k", b"a", b"b"],
            "returns": [],
        },
        {
            "name": "Check SDIFF value for existing key with non existing diff keys ",
            "command": "SDIFF",
            "args": [b"k", b"a", b"b"],
            "returns": list(set([b"1", b"2", b"3", b"4"])),
            "depends": [
                {"command": "SADD", "args": [b"k", b"1", b"2", b"3", b"4"], "returns": 4}
            ],
        },
        {
            "name": "Check SDIFF return value for existing key",
            "command": "SDIFF",
            "args": [b"k", b"a", b"b"],
            "returns": list(set([b"1", b"2", b"3"])),
            "depends": [
                {
                    "command": "SADD",
                    "args": [b"k", b"1", b"2", b"3", b"4", b"5", b"6", b"7", b"8", b"9"],
                    "returns": 9,
                },
                {
                    "command": "SADD",
                    "args": [b"a", b"4", b"5", b"6", b"7", b"8", b"9"],
                    "returns": 6,
                },
                {
                    "command": "SADD",
                    "args": [b"b", b"10", b"20", b"30", b"40"],
                    "returns": 4,
                },
            ],
        },
        {
            "name": "Check SDIFFSTORE value for non existing key",
            "command": "SDIFFSTORE",
            "args": [b"k", b"a", b"b", b"c"],
            "returns": 0,
        },
        {
            "name": "Check SDIFFSTORE value for existing key with non existing diff keys ",
            "command": "SDIFFSTORE",
            "args": [b"k", b"a", b"b", b"c"],
            "returns": 0,
            "depends": [
                {"command": "SADD", "args": [b"k", b"1", b"2", b"3", b"4"], "returns": 4}
            ],
        },
        {
            "name": "Check SDIFFSTORE value for existing key with some existing diff keys ",
            "command": "SDIFFSTORE",
            "args": [b"k", b"a", b"b", b"c"],
            "returns": 5,
            "depends": [
                {"command": "SADD", "args": [b"k", b"1", b"3", b"4"], "returns": 4},
                {
                    "command": "SADD",
                    "args": [b"a", b"10", b"20", b"30", b"40", b"50"],
                    "returns": 4,
                },
            ],
        },
        {
            "name": "Check SDIFFSTORE return value for existing key",
            "command": "SDIFFSTORE",
            "args": [b"k", b"a", b"b", b"c"],
            "returns": 2,
            "depends": [
                {
                    "command": "SADD",
                    "args": [b"a", b"1", b"2", b"3", b"4", b"5", b"6", b"7", b"8", b"9"],
                    "returns": 9,
                },
                {
                    "command": "SADD",
                    "args": [b"b", b"4", b"5", b"6", b"7", b"8", b"9"],
                    "returns": 6,
                },
                {
                    "command": "SADD",
                    "args": [b"c", b"2", b"10", b"20", b"30", b"40"],
                    "returns": 4,
                },
            ],
        },
        {
            "name": "Check SINTER value for non existing key",
            "command": "SINTER",
            "args": [b"k", b"a", b"b"],
            "returns": [],
        },
        {
            "name": "Check SINTER value for existing key with non existing inter keys ",
            "command": "SINTER",
            "args": [b"k", b"a", b"b"],
            "returns": [],
            "depends": [
                {"command": "SADD", "args": [b"k", b"1", b"2", b"3", b"4"], "returns": 4}
            ],
        },
        {
            "name": "Check SINTER return value for existing key",
            "command": "SINTER",
            "args": [b"k", b"a", b"b"],
            "returns": list(set([b"5", b"6"])),
            "depends": [
                {
                    "command": "SADD",
                    "args": [b"k", b"1", b"2", b"3", b"4", b"5", b"6", b"7", b"8", b"9"],
                    "returns": 9,
                },
                {
                    "command": "SADD",
                    "args": [b"a", b"4", b"5", b"6", b"7", b"8", b"9"],
                    "returns": 6,
                },
                {
                    "command": "SADD",
                    "args": [b"b", b"10", b"20", b"30", b"40", b"5", b"6"],
                    "returns": 4,
                },
            ],
        },
        {
            "name": "Check SINTERSTORE value for non existing key",
            "command": "SINTERSTORE",
            "args": [b"k", b"a", b"b", b"c"],
            "returns": 0,
        },
        {
            "name": "Check SINTERSTORE value for existing key with non existing diff keys ",
            "command": "SINTERSTORE",
            "args": [b"k", b"a", b"b", b"c"],
            "returns": 0,
            "depends": [
                {"command": "SADD", "args": [b"k", b"1", b"2", b"3", b"4"], "returns": 4}
            ],
        },
        {
            "name": "Check SINTERSTORE value for existing key with some existing diff keys ",
            "command": "SINTERSTORE",
            "args": [b"k", b"a", b"b"],
            "returns": 3,
            "depends": [
                {
                    "command": "SADD",
                    "args": [b"k", b"1", b"3", b"4", b"89"],
                    "returns": 4,
                },
                {
                    "command": "SADD",
                    "args": [b"a", b"10", b"20", b"30", b"40", b"50"],
                    "returns": 4,
                },
                {"command": "SADD", "args": [b"b", b"10", b"40", b"50"], "returns": 4},
            ],
        },
        {
            "name": "Check SISMEMBER with nonexisting key",
            "command": "SISMEMBER",
            "args": [b"k", b"a"],
            "returns": 0,
        },
        {
            "name": "Check SISMEMBER with nonmember value",
            "command": "SISMEMBER",
            "args": [b"k", b"a"],
            "returns": 0,
            "depends": [
                {"command": "SADD", "args": [b"k", b"1", b"3", b"4", b"89"], "returns": 4}
            ],
        },
        {
            "name": "Check SISMEMBER with existing value",
            "command": "SISMEMBER",
            "args": [b"k", b"a"],
            "returns": 1,
            "depends": [
                {
                    "command": "SADD",
                    "args": [b"k", b"1", b"3", b"a", b"4", b"89"],
                    "returns": 4,
                }
            ],
        },
        {
            "name": "Check SMOVE with nonexisting key",
            "command": "SMOVE",
            "args": [b"s", b"t", b"val"],
            "returns": 0,
        },
        {
            "name": "Check SMOVE with existing key nonmember value",
            "command": "SMOVE",
            "args": [b"s", b"t", b"val"],
            "returns": 0,
            "depends": [{"command": "SADD", "args": [b"s", b"notval"], "returns": 1}],
        },
        {
            "name": "Check SMOVE with member value non existing target",
            "command": "SMOVE",
            "args": [b"s", b"t", b"val"],
            "returns": 1,
            "depends": [{"command": "SADD", "args": [b"s", b"val"], "returns": 1}],
            "expects": lambda cmds: b"val" not in cmds.data[b"s"]
            and b"val" in cmds.data[b"t"],
        },
        {
            "name": "Check SMOVE with member value  existing target having the same value",
            "command": "SMOVE",
            "args": [b"s", b"t", b"val"],
            "returns": 1,
            "depends": [
                {"command": "SADD", "args": [b"s", b"val"], "returns": 1},
                {"command": "SADD", "args": [b"t", b"val"], "returns": 1},
            ],
            "expects": lambda cmds: b"val" not in cmds.data[b"s"]
            and b"val" in cmds.data[b"t"],
        },
        {
            "name": "Check SMOVE with member value  existing target not having the value",
            "command": "SMOVE",
            "args": [b"s", b"t", b"val"],
            "returns": 1,
            "depends": [
                {"command": "SADD", "args": [b"s", b"val"], "returns": 1},
                {"command": "SADD", "args": [b"t", b"notval"], "returns": 1},
            ],
            "expects": lambda cmds: b"val" not in cmds.data[b"s"]
            and b"val" in cmds.data[b"t"],
        },
        {
            "name": "Check SPOP with nonexisting key",
            "command": "SPOP",
            "args": [b"k"],
            "returns": NIL,
        },
        {
            "name": "Check SPOP with only existing key",
            "command": "SPOP",
            "args": [b"k"],
            "returns": b"1",
            "depends": [{"command": "SADD", "args": [b"k", b"1"], "returns": 1}],
        },
        {
            "name": "Check SPOP with a sample size less than set size",
            "command": "SPOP",
            "args": [b"k", b"3"],
            "returns": lambda rv, cs: set([b"1", b"2", b"3", b"4", b"5"]).issuperset(
                set(rv)
            ),
            "depends": [
                {
                    "command": "SADD",
                    "args": [b"k", b"1", b"2", b"3", b"4", b"5"],
                    "returns": 1,
                }
            ],
        },
        {
            "name": "Check SPOP with count bigger than set size",
            "command": "SPOP",
            "args": [b"k", b"3"],
            "returns": list(set([b"1", b"2"])),
            "depends": [{"command": "SADD", "args": [b"k", b"1", b"2"], "returns": 2}],
        },
        {
            "name": "Check SRANDMEMBER with nonexisting key",
            "command": "SRANDMEMBER",
            "args": [b"k"],
            "returns": NIL,
        },
        {
            "name": "Check SRANDMEMBER with only existing key",
            "command": "SRANDMEMBER",
            "args": [b"k"],
            "returns": b"1",
            "depends": [{"command": "SADD", "args": [b"k", b"1"], "returns": 1}],
        },
        {
            "name": "Check SRANDMEMBER with a sample size less than set size",
            "command": "SRANDMEMBER",
            "args": [b"k", b"3"],
            "returns": lambda rv, cs: cs.data[b"k"].issuperset(set(rv)),
            "depends": [
                {
                    "command": "SADD",
                    "args": [b"k", b"1", b"2", b"3", b"4", b"5"],
                    "returns": 1,
                }
            ],
        },
        {
            "name": "Check SRANDMEMBER with count bigger than set size",
            "command": "SRANDMEMBER",
            "args": [b"k", b"3"],
            "returns": list(set([b"1", b"2"])),
            "depends": [{"command": "SADD", "args": [b"k", b"1", b"2"], "returns": 2}],
        },
    ]

    for item in test_sequence:
        cs = Commands(data=Data())
        if "depends" in item:
            for d_item in item["depends"]:
                cmd = getattr(cs, d_item["command"])
                cmd(*d_item["args"])
        # real test here
        if "returns" in item:
            retval = getattr(cs, item["command"])(*item["args"])

            returns = item["returns"]
            if callable(returns):
                print(protocolParser(retval), cs.data, returns)
                assert returns(protocolParser(retval), cs)  # should return truthy
            else:
                assert retval == protocolBuilder(returns), item["name"]

        if "expects" in item:
            assert item["expects"](cs), f"expects of {item['name']}"
