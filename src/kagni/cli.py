"""Unified command line entry for the kagni servers.

One executable, two event-loop backends::

    kagni.py --loop asyncio|trio [--host HOST] [--port PORT]
             [--socket PATH] [--db PATH] [--dump-interval SECS]

TCP (host/port) and a unix domain socket (--socket) are additive, like
redis: ``--port 0`` disables the TCP listener for socket-only setups.
"""

import argparse
import importlib
import logging
import os
import socket

from kagni.commands import Commands
from kagni.data import Data
from kagni.db import DB

log = logging.getLogger("kagni")

DEFAULT_DB_PATH = os.environ.get("KAGNI_DB", "kagni.sqlite")
DEFAULT_HOST = "localhost"
DEFAULT_PORT = 6380
DEFAULT_DUMP_INTERVAL = 20


class Config:
    """Everything the server backends need to know about this run."""

    def __init__(self, loop, host, port, socket_path, db_path,
                 dump_interval, no_uvloop):
        self.loop = loop
        self.host = host
        self.port = port
        self.socket_path = socket_path
        self.db_path = db_path
        self.dump_interval = dump_interval
        self.no_uvloop = no_uvloop


# ------------------------------------------------------------ shared runtime
MEMORY_DB = ":memory:"


def is_memory_mode(db_path):
    """True when the store should live purely in RAM: no sqlite file, no
    snapshot dumps (sqlite's :memory: would be ephemeral per connection
    anyway, so skipping the machinery entirely is the honest mode)."""
    return db_path is None or db_path == MEMORY_DB


def build_runtime(db_path):
    """Create the store and wire up the command handler.  Shared by both
    backends.  Returns ``(db, data, handler)``; *db* is None in memory
    mode, which tells the engines to skip the dumper and final dump."""
    if is_memory_mode(db_path):
        log.info("in-memory mode: no sqlite file, no snapshots")
        data = Data()
        return None, data, Commands(data)

    db = DB(db_path)
    data = Data()
    try:
        snapshot = db.load()
    except Exception:
        log.exception("could not restore snapshot, starting empty")
    else:
        for key, value in snapshot.items():
            data[key] = value
        if len(data):
            log.info("restored %d keys", len(data))

    handler = Commands(data)
    handler.persistence = db
    return db, data, handler


# ------------------------------------------------------ unix socket helpers
def prepare_socket_path(path):
    """Remove a stale socket file left by a previous crash, so we can
    bind; refuse to start when a live server is already listening there."""
    if os.path.exists(path):
        probe = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            try:
                probe.connect(path)
            except ConnectionRefusedError:
                # nothing is listening: leftover file from a crashed run
                os.unlink(path)
            except FileNotFoundError:
                pass  # vanished between the exists() check and now
            else:
                raise RuntimeError(
                    "socket path %r is in use by a running server" % path
                )
        finally:
            probe.close()
    return path


def remove_socket_file(path):
    """Best-effort unlink of our own unix socket file on shutdown."""
    try:
        os.unlink(path)
    except FileNotFoundError:
        pass
    except OSError:
        log.warning("could not remove socket file %s", path, exc_info=True)


# ------------------------------------------------------------------- parser
def build_parser():
    parser = argparse.ArgumentParser(
        prog="kagni",
        description="Kagni — a Redis-like data store (RESP, sqlite snapshots).",
    )
    parser.add_argument(
        "--loop",
        choices=("asyncio", "trio"),
        default="asyncio",
        help="event loop backend (default: asyncio, uses uvloop when installed)",
    )
    parser.add_argument(
        "--host",
        default=DEFAULT_HOST,
        help="interface to bind the TCP listener to (default: %(default)s)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_PORT,
        help="TCP port to listen on; 0 disables TCP (default: %(default)s)",
    )
    parser.add_argument(
        "--socket",
        dest="socket_path",
        metavar="PATH",
        default=None,
        help="also listen on this unix domain socket (additive, like redis)",
    )
    parser.add_argument(
        "--db",
        dest="db_path",
        default=DEFAULT_DB_PATH,
        help=(
            "sqlite snapshot file (default: %(default)s, or $KAGNI_DB); "
            "use ':memory:' for a purely in-memory store with no snapshots"
        ),
    )
    parser.add_argument(
        "--dump-interval",
        type=int,
        default=DEFAULT_DUMP_INTERVAL,
        help="seconds between sqlite snapshots (default: %(default)s)",
    )
    parser.add_argument(
        "--no-uvloop",
        action="store_true",
        help="disable uvloop for the asyncio backend (ignored by trio)",
    )
    return parser


def _parse(argv):
    parser = build_parser()
    args = parser.parse_args(argv)

    if not 0 <= args.port <= 65535:
        parser.error("--port must be between 0 and 65535")
    if args.port == 0 and not args.socket_path:
        parser.error("nothing to listen on: pass --socket PATH when using --port 0")
    if args.dump_interval < 1:
        parser.error("--dump-interval must be at least 1 second")

    return Config(
        loop=args.loop,
        host=args.host,
        port=args.port,
        socket_path=args.socket_path,
        db_path=args.db_path,
        dump_interval=args.dump_interval,
        no_uvloop=args.no_uvloop,
    )


def main(argv=None):
    """Entry point (console script / kagni.py)."""
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s"
    )

    try:
        config = _parse(argv)
    except SystemExit:
        raise

    backend = "server_trio" if config.loop == "trio" else "server_asyncio"
    engine = importlib.import_module("kagni." + backend)
    try:
        engine.run(config)
    except KeyboardInterrupt:
        log.info("User requested shutdown.")
    except BaseExceptionGroup as group:
        # trio delivers SIGINT as a group wrapping KeyboardInterrupt
        if any(isinstance(exc, KeyboardInterrupt) for exc in group.exceptions):
            log.info("User requested shutdown.")
        else:
            log.exception("server exited with an error")
            return 1
    except Exception:
        log.exception("server exited with an error")
        return 1
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
