from kagni.constants import Response

__all__ = ["test_sequence"]

test_sequence = [
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
        "returns": lambda x, cs: set([b"1", b"a", b"3", b"7"]) == set(x),
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
        "returns": lambda x, cs: set([b"1", b"2", b"3", b"4"]) == set(x),
        "depends": [
            {"command": "SADD", "args": [b"k", b"1", b"2", b"3", b"4"], "returns": 4}
        ],
    },
    {
        "name": "Check SDIFF return value for existing key",
        "command": "SDIFF",
        "args": [b"k", b"a", b"b"],
        "returns": lambda x, cs: set([b"1", b"2", b"3"]) == set(x),
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
            {"command": "SADD", "args": [b"b", b"10", b"20", b"30", b"40"], "returns": 4},
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
        "returns": lambda x, cs: set([b"5", b"6"]) == set(x),
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
            {"command": "SADD", "args": [b"k", b"1", b"3", b"4", b"89"], "returns": 4},
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
        "returns": lambda rv, cs: set([b"1", b"2", b"3", b"4", b"5"]).issuperset(set(rv)),
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
        "returns": lambda x, cs: set([b"1", b"2"]) == set(x),
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
        "returns": lambda x, cs: set([b"1", b"2"]) == set(x),
        "depends": [{"command": "SADD", "args": [b"k", b"1", b"2"], "returns": 2}],
    },
]
