from kagni.commands import Commands
from kagni.data import Data
from kagni.constants import Response
from kagni.resp import protocolBuilder
from kagni.resp import protocolParser

from .basic_sequence import test_sequence as basic_sequence
from .bitops_sequence import test_sequence as bitops_sequence
from .hash_sequence import test_sequence as hash_sequence
from .set_sequence import test_sequence as set_sequence

# commands whose replies have no defined ordering in redis (set iteration
# order depends on the process-randomised byte hash, so the comparison
# must be order-insensitive)
UNORDERED = ("SMEMBERS", "SDIFF", "SINTER", "SUNION", "SPOP", "SRANDMEMBER")


def test_commands():
    test_sequence = (
        basic_sequence + bitops_sequence + hash_sequence + set_sequence
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
                assert returns(protocolParser(retval), cs)  # should return truthy
            elif item["command"] in UNORDERED and isinstance(returns, list):
                # compare as multisets (redis makes no ordering promise)
                assert sorted(protocolParser(retval)) == sorted(returns), item["name"]
            else:
                assert retval == protocolBuilder(returns), item["name"]

        if "expects" in item:
            assert item["expects"](cs), f"expects of {item['name']}"
