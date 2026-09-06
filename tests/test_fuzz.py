"""Random-byte fuzz for the RESP readers.

The invariant the servers rely on: however the bytes arrive (arbitrary
fragment sizes, pipelined garbage, hostile lengths), ``RESPReader.feed``
either yields well-formed messages or raises ``ProtocolError`` - never
anything else, and never after the connection is back at a boundary.
Deterministic seeds keep failures reproducible.
"""

import random

import pytest

from kagni.commands import Commands
from kagni.data import Data
from kagni.resp import RESPReader, ProtocolError

from .test_regressions import _readers  # one reader per parse engine


def _reader_engines():
    return [reader.engine for reader in _readers()]


def _fuzz_once(engine, data, seed):
    rng = random.Random(seed)
    reader = RESPReader(engine=engine)
    try:
        # split the blob into arbitrary fragments, like a socket would
        pos = 0
        while pos < len(data):
            chunk = data[pos:pos + rng.randint(1, 64)]
            pos += len(chunk)
            for message in reader.feed(chunk):
                # whatever parsed must be dispatchable without raising
                Commands(data=Data()).dispatch(message)
    except ProtocolError:
        return  # a clean protocol error: the server closes the connection
    except Exception as exc:  # pragma: no cover - the fuzz found a bug
        raise AssertionError(
            "reader %s crashed on seed %d with %r" % (reader.engine, seed, exc)
        ) from exc


def _blob(rng):
    """A random byte blob: mostly garbage, sometimes framed messages."""
    kind = rng.random()
    if kind < 0.4:
        # pure garbage, occasionally with CRLF / RESP markers sprinkled in
        alphabet = bytes(range(256))
        return bytes(rng.choice(alphabet) for _ in range(rng.randint(0, 300)))
    if kind < 0.7:
        # inline-command-shaped lines (the hiredis engine parses these
        # itself at message boundaries)
        words = [b"PING", b"SET", b"GET", b"DEL", b"", b" ", b"ZADD"]
        return b"\r\n".join(
            b" ".join(rng.choice(words) for _ in range(rng.randint(0, 6)))
            for _ in range(rng.randint(1, 5))
        ) + b"\r\n"
    # RESP-framed commands with random (often bogus) lengths and payloads
    commands = [b"PING", b"SET", b"GET", b"DEL", b"INCR", b"ECHO", b"COMMAND"]
    parts = []
    for _ in range(rng.randint(1, 5)):
        cmd = rng.choice(commands)
        parts.append(b"*%d\r\n" % rng.randint(-2, 6))
        for token in [cmd] + [b"%d" % rng.randint(0, 10**9) for _ in range(rng.randint(0, 3))]:
            parts.append(b"$%d\r\n" % rng.randint(-3, 40))
            parts.append(b"x" * min(max(rng.randint(-3, 40), 0), 40))
            parts.append(b"\r\n")
    return b"".join(parts)


@pytest.mark.parametrize("seed", range(300))
def test_resp_reader_fuzz_never_crashes(seed):
    rng = random.Random(seed)
    data = _blob(rng)
    for engine in _reader_engines():
        _fuzz_once(engine, data, seed)


@pytest.mark.parametrize("seed", range(50))
def test_resp_reader_fuzz_mutates_valid_commands(seed):
    """Valid commands with random bytes inserted anywhere must still
    only ever produce ProtocolError (never a hang, never a crash)."""
    rng = random.Random(seed)
    base = b"*3\r\n$3\r\nSET\r\n$1\r\nk\r\n$1\r\nv\r\n"
    for _ in range(10):
        pos = rng.randint(0, len(base))
        base = base[:pos] + bytes([rng.randint(0, 255)]) + base[pos:]
    for engine in _reader_engines():
        _fuzz_once(engine, base, seed)
