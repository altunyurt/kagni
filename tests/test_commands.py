from kagni.commands import COMMANDS
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
        {"command": b"COMMAND", "args": [], "returns": OK},
        {"command": b"PING", "args": [], "returns": PONG},
        {"command": b"SET", "args": [b"a", b"1"], "returns": OK},
        {"command": b"SET", "args": [b"b", b"16739234"], "returns": OK},
        {"command": b"SET", "args": [b"c", b"deneme yapiyorum"], "returns": OK},
        {
            "command": b"SET",
            "args": [b"d", "fıstıkçışahap".encode("utf-8")],
            "returns": OK,
        },
        {
            "command": b"MSET",
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
            "command": b"MGET",
            "args": [b"e", b"f", b"g"],
            "returns": [b"1", b"3424gshm", "fıstıkçışahap".encode("utf-8")],
        },
        {"command": b"DEL", "args": [b"e", b"f", b"g"], "returns": 3},

        ##
        # expire
        ##
        {
            "command": b"EXPIRE",
            "args": [b"e", b"10"],
            "returns": 1,
            "depends": [{"command": b"SET", "args": [b"e", b"1"], "returns": OK}],
        },
        {"command": b"EXPIRE", "args": [b"non-existent", b"10"], "returns": 0},
    ]

    for item in test_sequence:
        returns = COMMANDS[item["command"]](*item["args"])
        assert returns == protocolBuilder(item["returns"])
