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


async def _pubsub_writer(stream, receive_channel, send_lock, idle_event):
    """Drains pushed pub/sub frames and subscribed-mode replies to the
    socket.  Only active once the connection subscribes (the channel stays
    empty otherwise); every send holds the shared lock so pushes can never
    interleave with a reply mid-frame.  Sets *idle_event* whenever it has
    drained the channel, which lets the read task's direct reply path know
    no push can overtake it."""
    try:
        item = await receive_channel.receive()
        while True:
            await _locked_send(stream, item, send_lock)
            try:
                item = receive_channel.receive_nowait()
            except trio.WouldBlock:
                idle_event.set()
                item = await receive_channel.receive()
    except (trio.BrokenResourceError, trio.ClosedResourceError,
            trio.EndOfChannel):
        pass


async def _locked_send(stream, frames, send_lock):
    """send_all under the connection's send lock.  Uncontended locks skip
    the acquire/release checkpoints (the hot path - the writer task only
    wakes once the connection subscribes)."""
    try:
        send_lock.acquire_nowait()
    except trio.WouldBlock:
        await send_lock.acquire()
    try:
        await stream.send_all(frames)
    finally:
        send_lock.release()


async def _direct_send(stream, frames, send_lock, idle_event):
    """Write one or more reply frames straight from the read task.  When
    the writer task is mid-push (idle_event cleared) wait for it to drain
    first, so a reply can never overtake an earlier push on the wire."""
    if not idle_event.is_set():
        await idle_event.wait()
    await _locked_send(stream, frames, send_lock)


def _connection_closed(exc):
    """True when an exception only means the peer went away - possibly
    wrapped in a nursery ExceptionGroup (a peer resetting the socket
    while the writer task is mid-send surfaces as a group)."""
    if isinstance(exc, (trio.BrokenResourceError, trio.ClosedResourceError,
                        trio.Cancelled)):
        return True
    if isinstance(exc, BaseExceptionGroup):
        return all(_connection_closed(e) for e in exc.exceptions)
    return False


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
    # serializes every write to the stream: replies from the read task and
    # pushes from the writer task can never interleave mid-frame.  idle_event
    # is set whenever the writer has drained the channel; direct replies wait
    # on it so nothing can overtake a queued push.
    send_lock = trio.Lock()
    idle_event = trio.Event()
    idle_event.set()

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
                nursery.start_soon(
                    _pubsub_writer, stream, receive_channel, send_lock, idle_event
                )
                protocol_error = False
                while not protocol_error:
                    try:
                        data = await stream.receive_some(65536)
                        if not data:
                            return
                        # replies to an unsubscribed connection go straight to
                        # the socket, batched per chunk (a pipelined chunk is
                        # one send_all instead of one per command); a
                        # subscribed connection routes everything through the
                        # channel so pushes and confirmations keep their
                        # order.  A mid-chunk SUBSCRIBE flushes the direct
                        # replies first, a mid-chunk UNSUBSCRIBE leaves the
                        # channel to drain before direct replies resume.
                        direct = []
                        for request in parser.feed(data):
                            reply = command_handler.dispatch(request, session)
                            if reply is None:
                                continue
                            if session.subscribed:
                                if direct:
                                    await _direct_send(
                                        stream, b"".join(direct),
                                        send_lock, idle_event,
                                    )
                                    direct = []
                                idle_event.clear()
                                await send_channel.send(reply)
                            else:
                                direct.append(reply)
                        if direct:
                            await _direct_send(
                                stream, b"".join(direct), send_lock, idle_event
                            )
                    except ProtocolError as exc:
                        log.warning("protocol error: %s", exc)
                        error_line = (
                            b"-ERR Protocol error: " + str(exc).encode() + b"\r\n"
                        )
                        protocol_error = True
                    except (trio.BrokenResourceError, trio.ClosedResourceError):
                        # the peer reset the connection: a quiet exit, not
                        # an error (redis-benchmark and friends kill
                        # connections without a farewell)
                        return
                send_channel.close()
    except trio.Cancelled:
        pass  # slow-subscriber disconnect or shutdown
    except Exception as exc:
        # peer resets can surface here as a nursery ExceptionGroup when
        # the writer task hits the dead socket at the same moment
        if not _connection_closed(exc):
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
