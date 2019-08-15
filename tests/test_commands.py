from kagni.commands import Commands
from kagni.data import Data
from kagni.constants import Response
from kagni.resp import protocolBuilder
from kagni.resp import protocolParser
from random import choice
from string import ascii_letters
from string import hexdigits
import pytest


from .basic_sequence import test_sequence as basic_sequence

def test_commands():
    test_sequence = basic_sequence + [
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
            "returns": Response.NIL,
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
            "returns": Response.NIL,
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
                print(retval, cs.data, returns)
                print(protocolParser(retval), cs.data, returns)
                assert returns(protocolParser(retval), cs)  # should return truthy
            else:
                assert retval == returns, item["name"]

        if "expects" in item:
            assert item["expects"](cs), f"expects of {item['name']}"
