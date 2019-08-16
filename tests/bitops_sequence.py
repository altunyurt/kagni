__all__ = ["test_sequence"]

test_sequence = [
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
]
