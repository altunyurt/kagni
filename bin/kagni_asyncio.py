# /usr/bin/env python

import asyncio
import logging
import os
from functools import partial

try:
    import uvloop
except ImportError:  # uvloop is optional: plain asyncio still works
    uvloop = None

from kagni.commands import Commands
from kagni.data import Data
from kagni.db import DB
from kagni.resp import RESPReader, ProtocolError

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s"
)
log = logging.getLogger("kagni.asyncio")

DB_PATH = os.environ.get("KAGNI_DB", "kagni.sqlite")
DUMP_INTERVAL_SECS = 20


class RedisServerProtocol(asyncio.Protocol):
    """One RESPReader per connection provides correct framing: partial
    reads, pipelined commands and CRLF bytes inside bulk values all work,
    and protocol errors close the connection with a -ERR line instead of
    killing the loop."""

    def __init__(self, command_handler):
        self._handler = command_handler
        self._parser = RESPReader()
        self._transport = None

    def connection_made(self, transport):
        self._transport = transport

    def data_received(self, data):
        if self._transport is None:
            return
        try:
            for request in self._parser.feed(data):
                reply = self._handler.dispatch(request)
                if reply is not None:
                    self._transport.write(reply)
        except ProtocolError as exc:
            log.warning("protocol error: %s", exc)
            self._transport.write(
                b"-ERR Protocol error: " + str(exc).encode() + b"\r\n"
            )
            self._transport.close()

    def connection_lost(self, exc):
        self._transport = None


async def dumper(db, data):
    """Periodically snapshot the in-memory state to sqlite."""
    loop = asyncio.get_running_loop()
    while True:
        await asyncio.sleep(DUMP_INTERVAL_SECS)
        if not data:
            continue
        try:
            await loop.run_in_executor(None, db.dump, data)
        except Exception:
            log.exception("database dump failed")


def _restore(db, data):
    try:
        snapshot = db.load()
    except Exception:
        log.exception("could not restore snapshot, starting empty")
        return
    for key, value in snapshot.items():
        data[key] = value
    if len(data):
        log.info("restored %d keys", len(data))


async def amain(hostname="localhost", port=6380, db_path=DB_PATH):
    db = DB(db_path)
    data = Data()
    _restore(db, data)

    command_handler = Commands(data)
    command_handler.persistence = db

    loop = asyncio.get_running_loop()
    dumper_task = asyncio.create_task(dumper(db, data))
    try:
        server = await loop.create_server(
            partial(RedisServerProtocol, command_handler), hostname, port
        )
        log.info("kagni listening on %s:%s (db: %s)", hostname, port, db_path)
        async with server:
            await server.serve_forever()
    finally:
        dumper_task.cancel()
        try:
            await dumper_task
        except asyncio.CancelledError:
            pass
        try:
            await loop.run_in_executor(None, db.dump, data)
        except Exception:
            log.exception("final database dump failed")


def main(hostname="localhost", port=6380, db_path=DB_PATH):
    if uvloop is not None:
        uvloop.install()
    try:
        asyncio.run(amain(hostname, port, db_path))
    except KeyboardInterrupt:
        log.info("User requested shutdown.")
    return 0


def _parse_args(argv):
    hostname, port, db_path = "localhost", 6380, DB_PATH
    if argv:
        hostname = argv[0]
    if len(argv) > 1:
        port = int(argv[1])
    if len(argv) > 2:
        db_path = argv[2]
    return hostname, port, db_path


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 4:
        raise SystemExit("usage: kagni_asyncio.py [host] [port] [db_path]")
    main(*_parse_args(sys.argv[1:]))

# vim: set syntax=python
