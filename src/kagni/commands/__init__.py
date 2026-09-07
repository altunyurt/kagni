import logging

# the `.set` submodule import below shadows the builtin on this package,
# so the Session captures it up front
_builtin_set = set

from .basic import CommandSetMixin as BasicMixin
from .set import CommandSetMixin as SetMixin
from .bit import CommandSetMixin as BitMixin
from .hash import CommandSetMixin as HashMixin
from .lists import CommandSetMixin as ListMixin
from .zset import CommandSetMixin as ZSetMixin
from .pubsub import SUBSCRIBE_COMMANDS
from .pubsub import CommandSetMixin as PubSubMixin
from kagni.constants import Error, Errors, Response
from kagni.data import Data
from kagni.pubsub import PubSubHub
from kagni.resp import protocolBuilder

log = logging.getLogger(__name__)

__all__ = ["Commands", "Session"]


# RESP2 subscribed-mode rules (see _dispatch_direct)
_ALLOWED_WHILE_SUBSCRIBED = frozenset(
    ("SUBSCRIBE", "UNSUBSCRIBE", "PSUBSCRIBE", "PUNSUBSCRIBE", "PING")
)
_GATE_TEXT = (
    "Can't execute '%s': only (P|S)SUBSCRIBE / (P|S)UNSUBSCRIBE / PING / "
    "QUIT / RESET are allowed in this context"
)
_SUBCOMMAND_COMMANDS = frozenset(("CLIENT", "CONFIG", "COMMAND", "PUBSUB"))


def _gate_label(request):
    """redis labels subcommands in the gate error as 'name|sub' (e.g.
    'client|setname', 'pubsub|numpat')."""
    label = request[0].decode("ascii", "replace").lower()
    if len(request) > 1 and request[0].decode("ascii", "replace").upper() in _SUBCOMMAND_COMMANDS:
        label += "|" + request[1].decode("ascii", "replace").lower()
    return label


class Session:
    """Per-connection state: the MULTI/EXEC transaction queue and the
    pub/sub subscriptions.

    The servers create one Session per connection and pass it to
    ``Commands.dispatch``; without one, MULTI has nowhere to queue and
    pub/sub has no connection to attach to.  ``sender`` is wired by the
    server backends to write pushed frames (messages, subscribe
    confirmations); without one, frames collect in ``outbox`` (how the
    command layer is unit-tested).
    """

    __slots__ = ("in_multi", "queue", "channels", "patterns", "sender", "outbox")

    def __init__(self):
        self.in_multi = False
        self.queue = []
        self.channels = _builtin_set()
        self.patterns = _builtin_set()
        self.sender = None
        self.outbox = []

    @property
    def subscription_count(self):
        return len(self.channels) + len(self.patterns)

    @property
    def subscribed(self):
        return bool(self.channels or self.patterns)

    def deliver(self, frame):
        """Push one out-of-band frame (pub/sub message or confirmation)
        to this connection."""
        if self.sender is not None:
            self.sender(frame)
        else:
            self.outbox.append(frame)


class Commands(
    BasicMixin, SetMixin, BitMixin, HashMixin, ListMixin, ZSetMixin, PubSubMixin
):
    def __init__(self, data=None):
        self.data = data if data is not None else Data()
        # optional snapshot backend, wired by the servers; FLUSHDB/FLUSHALL
        # wipe it together with the in-memory state
        self.persistence = None
        # reported by INFO; the servers set it to the listening port
        self.tcp_port = 0
        # channel/pattern fan-out for pub/sub (no persistence involved)
        self.hub = PubSubHub()
        # the connection being served right now, for pub/sub handlers
        self._session = None

    # ------------------------------------------------------------ dispatch
    def dispatch(self, request, state=None):
        """Execute one parsed request (``[command, *args]``) and return the
        RESP reply bytes.

        *state* is the per-connection :class:`Session` (MULTI/EXEC queue
        and pub/sub subscriptions) when the caller has one.  Unknown
        commands and arity errors produce proper ``-ERR`` replies,
        command errors (``Error``) are encoded as RESP errors, and
        nothing here ever raises, so a bad request cannot kill the
        connection.  Returns None for empty requests and for pub/sub
        commands whose replies were pushed to the connection already.
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

    def _dispatch_direct(self, name, raw_name, request, state, bypass_gate=False):
        """Normal execution path (also replays one queued command during
        EXEC).  Returns a complete RESP wire frame (or None when the
        reply was pushed out-of-band), never raises."""
        session = state if state is not None else self._session
        if (
            not bypass_gate
            and session is not None
            and session.subscribed
            and name in ("MULTI", "DISCARD")
        ):
            # redis gates these before their own special handling
            return protocolBuilder(Error("ERR", _GATE_TEXT % _gate_label(request)))
        if name == "MULTI":
            if state is None:
                return protocolBuilder(
                    Error("ERR", "MULTI requires a per-connection session")
                )
            state.in_multi = True
            state.queue = []
            return protocolBuilder(Response.OK)
        if name == "EXEC":
            if session is not None and session.subscribed:
                # redis reports an aborted (never started) transaction
                return protocolBuilder(
                    Error(
                        "EXECABORT",
                        "Transaction discarded because of: "
                        + _GATE_TEXT % "exec",
                    )
                )
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

        # RESP2 subscribed-mode gate: with >=1 subscription only the
        # subscribe family and PING are allowed (QUIT/RESET do not
        # exist here); EXEC replays bypass it, like redis' execCommand
        if (
            not bypass_gate
            and session is not None
            and session.subscribed
            and name not in _ALLOWED_WHILE_SUBSCRIBED
        ):
            return protocolBuilder(Error("ERR", _GATE_TEXT % _gate_label(request)))

        if session is not None and session.subscribed and name == "PING":
            # inside subscribed mode PING answers a two-element array
            if len(args) > 1:
                return protocolBuilder(Errors.arity("ping"))
            return protocolBuilder([b"pong", args[0] if args else b""])

        if name in SUBSCRIBE_COMMANDS:
            # pub/sub handlers push their frames through the session and
            # return raw values (or None); they need the session bound
            previous = self._session
            self._session = session
            try:
                value = handler(*args)
            except Error as exc:
                return protocolBuilder(exc)
            except Exception:
                log.exception("command %r failed", raw_name)
                return protocolBuilder(Error("ERR", "internal error"))
            finally:
                self._session = previous
            return None if value is None else protocolBuilder(value)

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
            # runtime errors appear as inline -ERR entries, like redis.
            # A queued SUBSCRIBE pushes its confirmation through the
            # session: redis nests the first frame in the EXEC array and
            # emits any further frames right after it, so pushes are
            # captured per command and appended accordingly.
            parts = []
            trailing = []
            previous_sender = state.sender
            for request_ in queued:
                cmd = request_[0].decode("ascii", "replace")
                collector = []
                state.sender = collector.append
                try:
                    frame = self._dispatch_direct(
                        cmd.upper(), cmd, request_, state, bypass_gate=True
                    )
                finally:
                    state.sender = previous_sender
                if collector:
                    parts.append(collector[0])
                    trailing.extend(collector[1:])
                else:
                    parts.append(frame)
            return b"*%d\r\n" % len(queued) + b"".join(parts + trailing)

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
