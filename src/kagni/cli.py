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
import signal
import socket
import sys

from kagni import __version__
from kagni.commands import Commands
from kagni.data import Data
from kagni.db import DB

log = logging.getLogger("kagni")

DEFAULT_DB_PATH = os.environ.get("KAGNI_DB", "kagni.sqlite")
DEFAULT_HOST = "localhost"
# redis' own default port: kagni drops into setups that point at 6379;
# pass --port to run alongside a real redis on the same host
DEFAULT_PORT = 6379
DEFAULT_DUMP_INTERVAL = 20


class Config:
    """Everything the server backends need to know about this run."""

    def __init__(self, loop, host, port, socket_path, db_path,
                 dump_interval, no_uvloop, save=True, daemon=False,
                 pidfile=None, logfile=None):
        self.loop = loop
        self.host = host
        self.port = port
        self.socket_path = socket_path
        self.db_path = db_path
        self.dump_interval = dump_interval
        self.no_uvloop = no_uvloop
        self.save = save
        self.daemon = daemon
        self.pidfile = pidfile
        self.logfile = logfile


# ------------------------------------------------------------ shared runtime
MEMORY_DB = ":memory:"


def is_memory_mode(db_path):
    """True when the store should live purely in RAM: no sqlite file, no
    snapshot dumps (sqlite's :memory: would be ephemeral per connection
    anyway, so skipping the machinery entirely is the honest mode)."""
    return db_path is None or db_path == MEMORY_DB


def build_runtime(db_path, save=True):
    """Create the store and wire up the command handler.  Shared by both
    backends.  Returns ``(db, data, handler)``; *db* is None when there is
    nothing to snapshot (memory mode, or no-save without an existing
    file), which tells the engines to skip the dumper and final dump.

    With ``save=False`` (the --no-save flag, redis' ``save ""``) an
    existing snapshot file is still loaded at boot, but nothing is ever
    written back: no periodic dumps, no final dump, no file created when
    one is missing, and FLUSHDB only clears memory - the seed file stays
    pristine.
    """
    if is_memory_mode(db_path):
        log.info("in-memory mode: no sqlite file, no snapshots")
        data = Data()
        return None, data, Commands(data)

    if not save and not os.path.exists(db_path):
        log.info("no-save mode: no existing snapshot at %s, starting empty", db_path)
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
    if save:
        handler.persistence = db
    else:
        log.info("no-save mode: loading %s, snapshots disabled", db_path)
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
        "--version",
        action="version",
        version="%(prog)s " + __version__,
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
        "--no-save",
        action="store_false",
        dest="save",
        default=True,
        help=(
            "never write snapshots (redis 'save \"\"'): an existing --db "
            "file is still loaded at boot, but nothing is written back "
            "and FLUSHDB only clears memory"
        ),
    )
    parser.add_argument(
        "--no-uvloop",
        action="store_true",
        help="disable uvloop for the asyncio backend (ignored by trio)",
    )
    parser.add_argument(
        "--daemon",
        action="store_true",
        help="detach and run in the background (POSIX); the command returns "
        "immediately - use --logfile to keep the logs",
    )
    parser.add_argument(
        "--pidfile",
        metavar="PATH",
        default=None,
        help="write the process id to PATH; removed on graceful shutdown",
    )
    parser.add_argument(
        "--logfile",
        metavar="PATH",
        default=None,
        help="write logs to PATH instead of stderr",
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
        save=args.save,
        daemon=args.daemon,
        pidfile=args.pidfile,
        logfile=args.logfile,
    )


# ------------------------------------------------------- daemon plumbing
def _daemonize():
    """Detach from the controlling terminal: fork, let the parent exit,
    start a new session.  Returns only in the daemon child; stdin/stdout/
    stderr are redirected to /dev/null (use --logfile to keep logs)."""
    if not hasattr(os, "fork"):
        log.error("--daemon requires a POSIX platform (os.fork)")
        raise SystemExit(1)

    pid = os.fork()
    if pid > 0:
        print("kagni started as pid %d" % pid, flush=True)
        os._exit(0)

    os.setsid()
    devnull = os.open(os.devnull, os.O_RDWR)
    for fd in (0, 1, 2):
        os.dup2(devnull, fd)
    if devnull > 2:
        os.close(devnull)
    log.info("daemonized (pid %d)", os.getpid())


def _write_pidfile(path):
    try:
        with open(path, "w") as fh:
            fh.write("%d\n" % os.getpid())
    except OSError:
        log.exception("could not write pidfile %s", path)


def _remove_pidfile(path):
    try:
        os.unlink(path)
    except FileNotFoundError:
        pass
    except OSError:
        log.warning("could not remove pidfile %s", path, exc_info=True)


def _sigterm_handler(signum, frame):
    """SIGTERM handler for the asyncio backend: services stop daemons
    with SIGTERM; route it through the same graceful path as Ctrl-C so
    the final snapshot still happens.  (The trio backend handles SIGTERM
    with a signal receiver instead - raising KeyboardInterrupt from a
    signal handler at an arbitrary bytecode position corrupts trio's io
    bookkeeping.)"""
    raise KeyboardInterrupt


def _install_sigterm_handler():
    """Called by the asyncio backend only (see _sigterm_handler)."""
    signal.signal(signal.SIGTERM, _sigterm_handler)


def _restore_sigterm_handler():
    signal.signal(signal.SIGTERM, signal.SIG_DFL)


def _wraps_keyboard_interrupt(exc):
    """trio delivers SIGINT/SIGTERM wrapped in (possibly nested) exception
    groups: the native ExceptionGroup on Python 3.11+ (PEP 654) or the
    `exceptiongroup` backport below it.  Recurse so nested nursery groups
    are recognised as clean shutdowns too."""
    if isinstance(exc, KeyboardInterrupt):
        return True
    exceptions = getattr(exc, "exceptions", None)
    if not isinstance(exceptions, (list, tuple)):
        return False
    return any(_wraps_keyboard_interrupt(e) for e in exceptions)


def main(argv=None):
    """Entry point (console script / python -m kagni)."""
    config = _parse(argv)  # usage errors exit before any fork

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
        filename=config.logfile,
    )

    if config.daemon:
        _daemonize()
    if config.pidfile:
        _write_pidfile(config.pidfile)

    backend = "server_trio" if config.loop == "trio" else "server_asyncio"
    engine = importlib.import_module("kagni." + backend)
    # trio interrupts surface as BaseExceptionGroup on 3.11+; on 3.10 the
    # `exceptiongroup` backport provides the same type (trio depends on
    # it there), and plain groups are ordinary Exceptions below that
    if sys.version_info >= (3, 11):
        interrupted_group = (BaseExceptionGroup,)
    else:
        try:
            from exceptiongroup import BaseExceptionGroup as BackportGroup
        except ImportError:  # asyncio-only install without trio
            interrupted_group = (Exception,)
        else:
            interrupted_group = (BackportGroup, Exception)
    try:
        engine.run(config)
    except KeyboardInterrupt:
        log.info("User requested shutdown.")
    except interrupted_group as exc:
        if _wraps_keyboard_interrupt(exc):
            log.info("User requested shutdown.")
        else:
            log.exception("server exited with an error")
            return 1
    except Exception:
        log.exception("server exited with an error")
        return 1
    finally:
        if config.pidfile:
            _remove_pidfile(config.pidfile)
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
