import logging

from .basic import CommandSetMixin as BasicMixin
from .set import CommandSetMixin as SetMixin
from .bit import CommandSetMixin as BitMixin
from .hash import CommandSetMixin as HashMixin
from .lists import CommandSetMixin as ListMixin
from kagni.constants import Error, Errors, Response
from kagni.data import Data
from kagni.resp import protocolBuilder

log = logging.getLogger(__name__)

__all__ = ["Commands", "Session"]


class Session:
    """Per-connection state: the MULTI/EXEC transaction queue.

    The servers create one Session per connection and pass it to
    ``Commands.dispatch``; without one, MULTI has nowhere to queue.
    """

    __slots__ = ("in_multi", "queue")

    def __init__(self):
        self.in_multi = False
        self.queue = []


class Commands(BasicMixin, SetMixin, BitMixin, HashMixin, ListMixin):
    def __init__(self, data=None):
        self.data = data if data is not None else Data()
        # optional snapshot backend, wired by the servers; FLUSHDB/FLUSHALL
        # wipe it together with the in-memory state
        self.persistence = None

    # ------------------------------------------------------------ dispatch
    def dispatch(self, request, state=None):
        """Execute one parsed request (``[command, *args]``) and return the
        RESP reply bytes.

        *state* is the per-connection :class:`Session` (MULTI/EXEC queue)
        when the caller has one.  Unknown commands and arity errors
        produce proper ``-ERR`` replies, command errors (``Error``) are
        encoded as RESP errors, and nothing here ever raises, so a bad
        request cannot kill the connection.  Returns None for empty
        requests (no reply is sent).
        """
        if not isinstance(request, list) or not request:
            return None

        command = request[0]
        if not isinstance(command, bytes):
            return protocolBuilder(Error("ERR", "invalid request"))
        raw_name = command.decode("ascii", "replace")
        name = raw_name.upper()

        if state is not None and state.in_multi:
            return self._dispatch_queued(state, name, raw_name, request)
        return self._dispatch_direct(name, raw_name, request, state)

    def _dispatch_direct(self, name, raw_name, request, state):
        """Normal execution path (also replays one queued command during
        EXEC).  Returns a complete RESP wire frame, never raises."""
        if name == "MULTI":
            if state is None:
                return protocolBuilder(
                    Error("ERR", "MULTI requires a per-connection session")
                )
            state.in_multi = True
            state.queue = []
            return protocolBuilder(Response.OK)
        if name == "EXEC":
            return protocolBuilder(Error("ERR", "EXEC without MULTI"))
        if name == "DISCARD":
            return protocolBuilder(Error("ERR", "DISCARD without MULTI"))

        handler = getattr(self, name, None)
        if handler is None:
            return protocolBuilder(
                Error("ERR", "unknown command '{}'".format(raw_name))
            )

        args = request[1:]
        if len(args) < handler.min_args or (
            handler.max_args is not None and len(args) > handler.max_args
        ):
            return protocolBuilder(Errors.arity(name.lower()))

        try:
            return handler(*args)
        except Error as exc:
            return protocolBuilder(exc)
        except Exception:
            log.exception("command %r failed", raw_name)
            return protocolBuilder(Error("ERR", "internal error"))

    def _dispatch_queued(self, state, name, raw_name, request):
        """Command handling while a MULTI is open: queue valid commands
        (reply +QUEUED), surface immediate errors for unknown commands and
        arity mistakes without queueing them, and run EXEC/DISCARD."""
        if name == "EXEC":
            queued = state.queue
            state.queue = []
            state.in_multi = False
            if not queued:
                return protocolBuilder([])  # empty array, like redis
            # every queued dispatch returns a complete, self-delimiting
            # RESP frame, so the array reply is a plain concatenation;
            # runtime errors appear as inline -ERR entries, like redis
            parts = []
            for request_ in queued:
                cmd = request_[0].decode("ascii", "replace")
                parts.append(self._dispatch_direct(cmd.upper(), cmd, request_, None))
            return b"*%d\r\n" % len(queued) + b"".join(parts)

        if name == "DISCARD":
            state.queue = []
            state.in_multi = False
            return protocolBuilder(Response.OK)
        if name == "MULTI":
            return protocolBuilder(Error("ERR", "MULTI calls can not be nested"))

        # mirror the direct-path validation so queue-time errors are
        # answered immediately and the command is not queued
        handler = getattr(self, name, None)
        if handler is None:
            return protocolBuilder(
                Error("ERR", "unknown command '{}'".format(raw_name))
            )
        args = request[1:]
        if len(args) < handler.min_args or (
            handler.max_args is not None and len(args) > handler.max_args
        ):
            return protocolBuilder(Errors.arity(name.lower()))

        state.queue.append(request)
        return protocolBuilder(Response.QUEUED)
