# /usr/bin/env python

import logging
import os
from functools import partial

import trio

from kagni.commands import Commands
from kagni.data import Data
from kagni.db import DB
from kagni.resp import RESPReader, ProtocolError

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s"
)
log = logging.getLogger("kagni.trio")

DB_PATH = os.environ.get("KAGNI_DB", "kagni.sqlite")
DUMP_INTERVAL_SECS = 20


async def protocol_handler(stream, command_handler=None):
    """Per-connection RESP handler with incremental framing (partial
    reads / pipelining / CRLF-safe bulk values)."""
    parser = RESPReader()
    try:
        while True:
            data = await stream.receive_some(65536)
            if not data:
                return

            for request in parser.feed(data):
                reply = command_handler.dispatch(request)
                if reply is not None:
                    await stream.send_all(reply)
    except ProtocolError as exc:
        log.warning("protocol error: %s", exc)
        try:
            await stream.send_all(
                b"-ERR Protocol error: " + str(exc).encode() + b"\r\n"
            )
        except (trio.BrokenResourceError, trio.ClosedResourceError):
            pass
    except (trio.BrokenResourceError, trio.ClosedResourceError):
        pass
    except Exception:
        log.exception("connection handler failed")


async def dumper(db, data):
    """Periodically snapshot the in-memory state to sqlite, off the loop."""
    while True:
        await trio.sleep(DUMP_INTERVAL_SECS)
        if not data:
            continue
        try:
            await trio.to_thread.run_sync(db.dump, data)
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


async def main(hostname="localhost", port=6380, db_path=DB_PATH):
    db = DB(db_path)
    data = Data()
    _restore(db, data)

    command_handler = Commands(data)
    command_handler.persistence = db
    log.info("kagni listening on %s:%s (db: %s)", hostname, port, db_path)

    try:
        async with trio.open_nursery() as nursery:
            nursery.start_soon(dumper, db, data)
            nursery.start_soon(
                partial(
                    trio.serve_tcp,
                    partial(protocol_handler, command_handler=command_handler),
                    port,
                    host=hostname,
                )
            )
    finally:
        # best-effort final snapshot on shutdown
        try:
            db.dump(data)
        except Exception:
            log.exception("final database dump failed")
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
        raise SystemExit("usage: kagni_trio.py [host] [port] [db_path]")
    try:
        trio.run(main, *_parse_args(sys.argv[1:]))
    except KeyboardInterrupt:
        log.info("User requested shutdown.")

# vim: set filetype=python
