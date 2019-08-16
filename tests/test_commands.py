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
from .bitops_sequence import test_sequence as bitops_sequence
from .hash_sequence import test_sequence as hash_sequence
from .set_sequence import test_sequence as set_sequence


def test_commands():
    test_sequence = (
        basic_sequence
        + bitops_sequence
        + hash_sequence
        + set_sequence
    )

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
                assert returns(retval, cs)  # should return truthy
            else:
                assert retval == returns, item["name"]

        if "expects" in item:
            assert item["expects"](cs), f"expects of {item['name']}"
