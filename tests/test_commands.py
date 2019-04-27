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
    ]

    for item in test_sequence:
        cs = Commands(data=Data())
        if "depends" in item:
            for d_item in item["depends"]:
                cmd = getattr(cs, d_item["command"])
                cmd(*d_item["args"])
        # real test here
        returns = getattr(cs, item["command"])(*item["args"])
        assert returns == protocolBuilder(item["returns"]), item["name"]

        if "expects" in item:
            assert item["expects"](cs), item["expects"]
