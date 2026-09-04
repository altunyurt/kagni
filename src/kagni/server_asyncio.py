"""asyncio (+ optional uvloop) backend for kagni."""

import asyncio
import logging
from functools import partial

try:
    import uvloop
except ImportError:  # uvloop is optional: plain asyncio still works
    uvloop = None

from kagni.cli import build_runtime, prepare_socket_path, remove_socket_file
from kagni.resp import RESPReader, ProtocolError

log = logging.getLogger("kagni.asyncio")


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


async def dumper(db, data, interval):
    """Periodically snapshot the in-memory state to sqlite."""
    loop = asyncio.get_running_loop()
    while True:
        await asyncio.sleep(interval)
        if not data:
            continue
        try:
            await loop.run_in_executor(None, db.dump, data)
        except Exception:
            log.exception("database dump failed")


async def amain(config):
    db, data, handler = build_runtime(config.db_path)
    loop = asyncio.get_running_loop()
    factory = partial(RedisServerProtocol, handler)
    store = "in-memory" if db is None else config.db_path

    servers = []
    created_socket = None
    dumper_task = None
    try:
        if config.port > 0:
            servers.append(await loop.create_server(factory, config.host, config.port))
            log.info("kagni listening on %s:%s (db: %s)", config.host, config.port, store)
        if config.socket_path is not None:
            path = prepare_socket_path(config.socket_path)
            servers.append(await loop.create_unix_server(factory, path=path))
            created_socket = path
            log.info("kagni listening on %s (db: %s)", path, store)

        if db is not None:
            dumper_task = asyncio.create_task(dumper(db, data, config.dump_interval))
        await asyncio.gather(*(server.serve_forever() for server in servers))
    finally:
        for server in servers:
            server.close()
        if servers:
            await asyncio.gather(
                *(server.wait_closed() for server in servers), return_exceptions=True
            )
        if dumper_task is not None:
            dumper_task.cancel()
            try:
                await dumper_task
            except asyncio.CancelledError:
                pass
        if db is not None:
            try:
                await loop.run_in_executor(None, db.dump, data)
            except Exception:
                log.exception("final database dump failed")
        if created_socket is not None:
            remove_socket_file(created_socket)


def run(config):
    """Synchronous entry point used by kagni.cli.main."""
    if uvloop is not None and not config.no_uvloop:
        uvloop.install()
    return asyncio.run(amain(config))
