"""Shared helpers for the kagni test suite (one vocabulary everywhere)."""

from kagni.commands import Commands
from kagni.constants import Error
from kagni.data import Data
from kagni.resp import RESPReader

__all__ = ["_commands", "_expect_error", "_readers"]


def _commands():
    return Commands(data=Data())


def _expect_error(callable_, class_="ERR"):
    try:
        callable_()
    except Error as exc:
        assert exc.class_ == class_, "expected %r error, got %r" % (class_, exc.class_)
        return exc
    raise AssertionError("expected an Error to be raised")


def _readers():
    """One RESPReader per parse engine (pure python, plus hiredis when
    the optional C accelerator is installed)."""
    readers = [RESPReader(engine="python")]
    try:
        readers.append(RESPReader(engine="hiredis"))
    except ValueError:
        pass
    return readers
