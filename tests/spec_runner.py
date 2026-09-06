"""Shared executor for the per-command spec tables.

The former bespoke table runner (tests/test_commands.py) is gone; the
tables now live in the ``tests/test_*_spec.py`` modules as plain
parametrize inputs, and every row runs as its own pytest case through
:func:`run_spec_item`.  The semantics are unchanged:

- one fresh store per row, with ``depends`` entries replayed as setup
- ``returns`` compares the raw wire reply, or the parsed reply when the
  value is callable; replies of set commands (whose member order redis
  does not promise) compare as sorted multisets
- ``expects`` is a final assertion over the store
"""

from kagni.commands import Commands
from kagni.data import Data
from kagni.resp import protocolBuilder
from kagni.resp import protocolParser

# commands whose replies have no defined ordering in redis (set
# iteration order depends on the process-randomised byte hash, so the
# comparison must be order-insensitive)
UNORDERED = ("SMEMBERS", "SDIFF", "SINTER", "SUNION", "SPOP", "SRANDMEMBER")


def new_commands():
    return Commands(data=Data())


def run_spec_item(item):
    """Execute one spec-table row (a {command, args, depends, returns,
    expects, name} dict) and assert its contract."""
    cs = new_commands()
    for d_item in item.get("depends", ()):
        cmd = getattr(cs, d_item["command"])
        cmd(*d_item["args"])

    if "returns" in item:
        retval = getattr(cs, item["command"])(*item["args"])
        returns = item["returns"]
        if callable(returns):
            assert returns(protocolParser(retval), cs), item["name"]
        elif item["command"] in UNORDERED and isinstance(returns, list):
            # compare as multisets (redis makes no ordering promise)
            assert sorted(protocolParser(retval)) == sorted(returns), item["name"]
        else:
            assert retval == protocolBuilder(returns), item["name"]

    if "expects" in item:
        assert item["expects"](cs), "expects of %s" % item["name"]
