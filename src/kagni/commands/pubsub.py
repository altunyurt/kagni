"""Redis pub/sub commands (RESP2, like the rest of the server).

Subscriptions are per-connection state on the Session; the shared
PubSubHub fans messages out.  Confirmation and message frames are
pushed through the session's ``sender`` (or collected in its ``outbox``
when no connection is attached), so these handlers return None to the
request/reply path - except PUBLISH (an integer) and PUBSUB (its
introspection replies).  Dispatch-level rules live in Commands: the
RESP2 subscribed-mode gate (only (P|S)SUBSCRIBE / (P|S)UNSUBSCRIBE /
PING allowed once a client holds a subscription) and PING's two-element
reply inside subscribed mode.
"""

from kagni.constants import Error, Errors, Response
from kagni.resp import protocolBuilder

__all__ = ["CommandSetMixin"]

# the six pub/sub commands: routed by Commands through the session, not
# through the generic decorator pipeline (their replies are pushes)
SUBSCRIBE_COMMANDS = {
    "SUBSCRIBE", "UNSUBSCRIBE", "PSUBSCRIBE", "PUNSUBSCRIBE",
    "PUBLISH", "PUBSUB",
}


def pubsub_command(name, min_args):
    """Metadata-only marker: sets the attributes the dispatch arity
    check and the COMMAND table read (no reply encoding - these
    handlers return raw values or None)."""

    def decorate(fn):
        fn.command_name = name
        fn.min_args = min_args
        fn.max_args = None
        return fn

    return decorate


def _session(instance):
    session = getattr(instance, "_session", None)
    if session is None:
        raise Error("ERR", "pub/sub commands need a per-connection session")
    return session


class CommandSetMixin:

    @pubsub_command(b"SUBSCRIBE", 1)
    def SUBSCRIBE(self, *channels):
        """SUBSCRIBE channel [channel ...]: one [subscribe, channel,
        count] confirmation per channel, delivered to the connection."""
        session = _session(self)
        for channel in channels:
            session.channels.add(channel)
            self.hub.subscribe(session, channel)
            session.deliver(
                protocolBuilder([b"subscribe", channel, session.subscription_count])
            )

    @pubsub_command(b"UNSUBSCRIBE", 0)
    def UNSUBSCRIBE(self, *channels):
        """UNSUBSCRIBE [channel ...]: no arguments unsubscribes from
        every channel.  Every named channel (even one never subscribed)
        gets its own confirmation; a bare unsubscribe with no channel
        subscriptions confirms with a null channel and the remaining
        subscription count."""
        session = _session(self)
        had_channels = bool(session.channels)
        for channel in list(channels) or sorted(session.channels):
            session.channels.discard(channel)
            self.hub.unsubscribe(session, channel)
            session.deliver(
                protocolBuilder([b"unsubscribe", channel, session.subscription_count])
            )
        if not channels and not had_channels:
            session.deliver(
                protocolBuilder([b"unsubscribe", Response.NIL, session.subscription_count])
            )

    @pubsub_command(b"PSUBSCRIBE", 1)
    def PSUBSCRIBE(self, *patterns):
        """PSUBSCRIBE pattern [pattern ...]: like SUBSCRIBE, but the
        names are glob patterns matched against published channels."""
        session = _session(self)
        for pattern in patterns:
            session.patterns.add(pattern)
            self.hub.psubscribe(session, pattern)
            session.deliver(
                protocolBuilder([b"psubscribe", pattern, session.subscription_count])
            )

    @pubsub_command(b"PUNSUBSCRIBE", 0)
    def PUNSUBSCRIBE(self, *patterns):
        """PUNSUBSCRIBE [pattern ...]: no arguments unsubscribes from
        every pattern."""
        session = _session(self)
        had_patterns = bool(session.patterns)
        for pattern in list(patterns) or sorted(session.patterns):
            session.patterns.discard(pattern)
            self.hub.punsubscribe(session, pattern)
            session.deliver(
                protocolBuilder([b"punsubscribe", pattern, session.subscription_count])
            )
        if not patterns and not had_patterns:
            session.deliver(
                protocolBuilder([b"punsubscribe", Response.NIL, session.subscription_count])
            )

    @pubsub_command(b"PUBLISH", 2)
    def PUBLISH(self, channel, message):
        """PUBLISH channel message: fan the message out to every
        matching subscriber; replies with the number of delivered
        frames (redis counts deliveries, not distinct clients)."""
        return self.hub.publish(channel, message)

    @pubsub_command(b"PUBSUB", 1)
    def PUBSUB(self, *args):
        """PUBSUB CHANNELS [pattern] | NUMSUB [channel ...] | NUMPAT."""
        if not args:
            raise Errors.arity("pubsub")
        sub = args[0].upper()
        if sub == b"CHANNELS":
            if len(args) == 1:
                return self.hub.active_channels()
            if len(args) == 2:
                return self.hub.active_channels(args[1])
            raise Errors.SYNTAX
        if sub == b"NUMSUB":
            reply = []
            for channel in args[1:]:
                reply.extend((channel, self.hub.numsub(channel)))
            return reply
        if sub == b"NUMPAT" and len(args) == 1:
            return self.hub.numpatterns()
        name = args[0].decode("ascii", "replace")
        raise Error("ERR", "unknown subcommand '%s'. Try PUBSUB HELP." % name)
