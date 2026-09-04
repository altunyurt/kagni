"""trio backend for kagni."""

import logging
from functools import partial

import trio

from kagni.cli import build_runtime, prepare_socket_path, remove_socket_file
from kagni.resp import RESPReader, ProtocolError

log = logging.getLogger("kagni.trio")


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


async def dumper(db, data, interval):
    """Periodically snapshot the in-memory state to sqlite, off the loop."""
    while True:
        await trio.sleep(interval)
        if not data:
            continue
        try:
            await trio.to_thread.run_sync(db.dump, data)
        except Exception:
            log.exception("database dump failed")


async def amain(config):
    db, data, handler = build_runtime(config.db_path, save=config.save)
    store = "in-memory" if db is None else config.db_path

    listeners = []
    created_socket = None
    try:
        if config.port > 0:
            listeners += await trio.open_tcp_listeners(config.port, host=config.host)
            log.info("kagni listening on %s:%s (db: %s)", config.host, config.port, store)
        if config.socket_path is not None:
            path = prepare_socket_path(config.socket_path)
            sock = trio.socket.socket(trio.socket.AF_UNIX, trio.socket.SOCK_STREAM)
            await sock.bind(path)
            sock.listen(16)
            listeners.append(trio.SocketListener(sock))
            created_socket = path
            log.info("kagni listening on %s (db: %s)", path, store)

        async with trio.open_nursery() as nursery:
            if db is not None and config.save:
                nursery.start_soon(dumper, db, data, config.dump_interval)
            nursery.start_soon(
                trio.serve_listeners,
                partial(protocol_handler, command_handler=handler),
                listeners,
            )
    finally:
        if db is not None and config.save:
            # best-effort final snapshot on shutdown (serve_listeners closed
            # the listeners when the nursery was cancelled)
            try:
                db.dump(data)
            except Exception:
                log.exception("final database dump failed")
        if created_socket is not None:
            remove_socket_file(created_socket)


def run(config):
    """Synchronous entry point used by kagni.cli.main."""
    return trio.run(amain, config)
