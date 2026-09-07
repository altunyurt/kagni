"""trio backend for kagni."""

import logging
import signal
from functools import partial

import trio

from kagni.cli import build_runtime, prepare_socket_path, remove_socket_file
from kagni.commands import Session
from kagni.resp import RESPReader, ProtocolError

log = logging.getLogger("kagni.trio")


# pub/sub pushes are queued here before hitting the socket; a subscriber
# that stops reading fills the queue and is disconnected (redis drops
# slow pub/sub clients too)
_PUBSUB_QUEUE = 4096


async def _pubsub_writer(stream, receive_channel):
    """Drains pushed pub/sub frames to the socket (all writes go through
    this task so pushes and replies cannot interleave)."""
    try:
        async for frame in receive_channel:
            await stream.send_all(frame)
    except (trio.BrokenResourceError, trio.ClosedResourceError):
        pass


async def protocol_handler(stream, command_handler=None):
    """Per-connection RESP handler with incremental framing (partial
    reads / pipelining / CRLF-safe bulk values).  All writes - replies
    and pub/sub pushes - go through one writer task so they cannot
    interleave on the socket; a subscriber that stops reading fills the
    push queue and is disconnected."""
    parser = RESPReader()
    session = Session()  # per-connection MULTI/EXEC state
    send_channel, receive_channel = trio.open_memory_channel(_PUBSUB_QUEUE)
    scope = trio.CancelScope()

    def push_frame(frame):
        """Out-of-band write for pub/sub pushes; a full queue means the
        subscriber is not reading - disconnect it, like redis."""
        try:
            send_channel.send_nowait(frame)
        except trio.WouldBlock:
            log.warning("disconnecting slow pub/sub subscriber")
            scope.cancel()
        except trio.BrokenResourceError:
            pass

    session.sender = push_frame
    error_line = None
    try:
        with scope:
            async with trio.open_nursery() as nursery:
                nursery.start_soon(_pubsub_writer, stream, receive_channel)
                protocol_error = False
                while not protocol_error:
                    try:
                        data = await stream.receive_some(65536)
                        if not data:
                            return
                        for request in parser.feed(data):
                            reply = command_handler.dispatch(request, session)
                            if reply is not None:
                                await send_channel.send(reply)
                    except ProtocolError as exc:
                        log.warning("protocol error: %s", exc)
                        error_line = (
                            b"-ERR Protocol error: " + str(exc).encode() + b"\r\n"
                        )
                        protocol_error = True
                send_channel.close()
    except trio.Cancelled:
        pass  # slow-subscriber disconnect or shutdown
    except (trio.BrokenResourceError, trio.ClosedResourceError):
        pass
    except Exception:
        log.exception("connection handler failed")
    finally:
        command_handler.hub.remove_session(session)
        session.sender = None
        send_channel.close()
    if error_line is not None:
        # the writer task has ended: send the protocol error directly
        try:
            await stream.send_all(error_line)
        except (trio.BrokenResourceError, trio.ClosedResourceError):
            pass


async def dumper(db, data, interval):
    """Periodically snapshot the in-memory state to sqlite, off the loop.

    The consistent copy is taken on the trio thread (the single mutator)
    and only the sqlite commit runs in a worker thread; the commit
    carries the epoch the snapshot was taken in, so a snapshot that
    predates a FLUSHDB stands down instead of resurrecting flushed keys.
    """
    while True:
        await trio.sleep(interval)
        snapshot = data.snapshot()
        if not snapshot:
            continue
        try:
            await trio.to_thread.run_sync(db.dump, snapshot, data, data.epoch)
        except Exception:
            log.exception("database dump failed")


async def _sigterm_watcher(cancel_scope):
    """Graceful SIGTERM for trio: cancel the serving nursery from inside
    the run so trio unwinds at safe checkpoints (raising KeyboardInterrupt
    from a signal handler corrupts trio's io bookkeeping).  Runs as a
    nursery child so trio's own SIGINT handling is unaffected."""
    with trio.open_signal_receiver(signal.SIGTERM) as signals:
        async for _ in signals:
            log.info("SIGTERM received, shutting down")
            cancel_scope.cancel()


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
            nursery.start_soon(_sigterm_watcher, nursery.cancel_scope)
    finally:
        if db is not None and config.save:
            # best-effort final snapshot on shutdown (serve_listeners closed
            # the listeners when the nursery was cancelled)
            try:
                db.dump(data.snapshot(), data, data.epoch)
            except Exception:
                log.exception("final database dump failed")
        if created_socket is not None:
            remove_socket_file(created_socket)


def run(config):
    """Synchronous entry point used by kagni.cli.main."""
    return trio.run(amain, config)
