"""Run a kagni server inside your own event loop - no subprocess.

The project premise is a real Redis-protocol endpoint for applications
and their tests, and embedding is the direct form of that: the server
shares the caller's loop (asyncio or trio, whichever is running), on an
ephemeral port, with nothing on disk unless you ask for a snapshot
file::

    # asyncio app
    async with kagni.embed.serve() as server:
        r = redis.asyncio.Redis(host=server.host, port=server.port)
        ...

    # trio app - same call, the running loop is detected
    async with kagni.embed.serve() as server:
        ...

The handle yields ``host``/``port``/``url``; exiting the block stops
the server (closes listeners and connections, stops the snapshot
dumper and writes the final dump when a snapshot file is configured).

For tests that want a subprocess instead (their own process keeps its
own loop and a sync redis-py client can block freely), see
``kagni.testing.start_server``.
"""

import asyncio
from contextlib import asynccontextmanager
from functools import partial

import trio

from kagni.cli import DEFAULT_DUMP_INTERVAL, build_runtime
from kagni.server_asyncio import RedisServerProtocol, dumper as _asyncio_dumper
from kagni.server_trio import dumper as _trio_dumper
from kagni.server_trio import protocol_handler as _trio_handler

__all__ = ["ServerHandle", "serve"]


class ServerHandle:
    """A running in-process server: ``host``/``port``/``url`` to connect.

    Stop the server by exiting the ``async with serve()`` block that
    produced it.
    """

    def __init__(self, host, port):
        self.host = host
        self.port = port

    @property
    def url(self):
        return "redis://%s:%d" % (self.host, self.port)


class _Serve:
    """Context manager picked at ``__aenter__`` time, so ``serve()`` can
    be called without knowing which loop is running (or force one with
    ``loop="asyncio"`` / ``loop="trio"``)."""

    def __init__(self, loop, host, db_path, save, dump_interval):
        self.loop = loop
        self.host = host
        self.db_path = db_path
        self.save = save
        self.dump_interval = dump_interval
        self._impl = None

    async def __aenter__(self):
        loop = self.loop
        if loop == "auto":
            try:
                asyncio.get_running_loop()
                loop = "asyncio"
            except RuntimeError:
                try:
                    trio.lowlevel.current_task()
                    loop = "trio"
                except Exception:
                    raise RuntimeError(
                        "kagni.embed.serve() must be called from inside a running "
                        "asyncio or trio event loop"
                    )
        if loop == "asyncio":
            self._impl = _serve_asyncio(
                self.host, self.db_path, self.save, self.dump_interval
            )
        elif loop == "trio":
            self._impl = _serve_trio(
                self.host, self.db_path, self.save, self.dump_interval
            )
        else:
            raise ValueError("unknown loop %r (use 'auto', 'asyncio' or 'trio')" % loop)
        return await self._impl.__aenter__()

    async def __aexit__(self, *exc_info):
        if self._impl is not None:
            return await self._impl.__aexit__(*exc_info)
        return None


def serve(loop="auto", host="127.0.0.1", db_path=":memory:", save=True,
          dump_interval=DEFAULT_DUMP_INTERVAL):
    """Run a kagni server inside the caller's event loop.

    *loop* is ``"auto"`` (detect asyncio/trio from the running context),
    ``"asyncio"`` or ``"trio"``.  *db_path* ``":memory:"`` (default)
    keeps everything in RAM; a file path enables sqlite snapshots with
    *save*, dumped every *dump_interval* seconds and once more on exit.
    """
    return _Serve(loop, host, db_path, save, dump_interval)


@asynccontextmanager
async def _serve_asyncio(host, db_path, save, dump_interval):
    db, data, handler = build_runtime(db_path, save=save)
    transports = set()

    class _Protocol(RedisServerProtocol):
        # track active transports so stop() can close client connections
        # (Server.wait_closed only returns once they are gone)
        def connection_made(self, transport):
            transports.add(transport)
            super().connection_made(transport)

        def connection_lost(self, exc):
            transports.discard(self._transport)
            super().connection_lost(exc)

    loop = asyncio.get_running_loop()
    server = await loop.create_server(
        partial(_Protocol, handler), host, 0  # 0 = ephemeral port
    )
    port = server.sockets[0].getsockname()[1]
    handler.tcp_port = port
    dumper_task = None
    if db is not None and save:
        dumper_task = asyncio.create_task(_asyncio_dumper(db, data, dump_interval))
    try:
        yield ServerHandle(host, port)
    finally:
        server.close()
        for transport in list(transports):
            transport.close()
        await server.wait_closed()
        if dumper_task is not None:
            dumper_task.cancel()
            try:
                await dumper_task
            except asyncio.CancelledError:
                pass
        if db is not None and save:
            # final snapshot, off the loop like the periodic dumper
            await loop.run_in_executor(
                None, db.dump, data.snapshot(), data, data.epoch
            )


@asynccontextmanager
async def _serve_trio(host, db_path, save, dump_interval):
    db, data, handler = build_runtime(db_path, save=save)
    listeners = await trio.open_tcp_listeners(0, host=host)
    port = listeners[0].socket.getsockname()[1]
    handler.tcp_port = port
    async with trio.open_nursery() as nursery:
        if db is not None and save:
            nursery.start_soon(_trio_dumper, db, data, dump_interval)
        nursery.start_soon(
            trio.serve_listeners,
            partial(_trio_handler, command_handler=handler),
            listeners,
        )
        try:
            yield ServerHandle(host, port)
        finally:
            # cancelling the nursery closes the listeners and every
            # per-connection handler (they remove their sessions)
            nursery.cancel_scope.cancel()
    if db is not None and save:
        # final snapshot, mirroring the trio CLI shutdown path
        db.dump(data.snapshot(), data, data.epoch)
