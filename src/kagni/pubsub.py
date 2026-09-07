"""In-memory pub/sub hub: channel/pattern fan-out between connections.

Pub/sub lives entirely outside the key-value store: no Data, no
snapshots, no expiry.  Subscribers are per-connection Session objects
carrying a ``sender`` (wired by each server backend); the hub routes
published messages to every matching subscriber.  Deliveries are
fire-and-forget with a per-backend slow-consumer policy (redis drops a
subscriber whose output buffer exceeds the pubsub limit).

RESP2 message frames (all plain arrays, like redis):
    [message, channel, payload]          channel subscribers
    [pmessage, pattern, channel, payload]  pattern subscribers
A client subscribed to a channel *and* matching patterns receives one
frame per subscription type that matches, and PUBLISH counts every
delivered frame (so one client on two matching patterns counts twice).
"""

from kagni.commands.common import compile_glob

__all__ = ["PubSubHub"]


class PubSubHub:

    def __init__(self):
        self._channels = {}   # channel bytes -> {Session}
        self._patterns = {}   # pattern bytes -> {Session}
        self._matchers = {}   # pattern -> compiled regex, lazily

    # ------------------------------------------------------------ subscribe
    def subscribe(self, session, channel):
        self._channels.setdefault(channel, set()).add(session)

    def unsubscribe(self, session, channel):
        subscribers = self._channels.get(channel)
        if subscribers is None:
            return
        subscribers.discard(session)
        if not subscribers:
            del self._channels[channel]

    def psubscribe(self, session, pattern):
        self._patterns.setdefault(pattern, set()).add(session)

    def punsubscribe(self, session, pattern):
        subscribers = self._patterns.get(pattern)
        if subscribers is None:
            return
        subscribers.discard(session)
        if not subscribers:
            del self._patterns[pattern]

    def remove_session(self, session):
        """Drop a disconnected session from every channel and pattern."""
        for table in (self._channels, self._patterns):
            for name, subscribers in list(table.items()):
                subscribers.discard(session)
                if not subscribers:
                    del table[name]

    # ------------------------------------------------------------- publish
    def publish(self, channel, payload):
        """Deliver *payload* on *channel*; returns how many frames were
        sent (redis counts deliveries, so one client subscribed via a
        channel and matching patterns counts once per delivered frame).

        Frames are written through each subscriber's ``sender`` (or its
        ``outbox`` when no connection is attached, e.g. in tests)."""
        receivers = 0
        for session in list(self._channels.get(channel, ())):
            session.deliver(build_message(channel, payload))
            receivers += 1
        for pattern in self._patterns:
            matcher = self._matchers.get(pattern)
            if matcher is None:
                matcher = compile_glob(pattern)
                self._matchers[pattern] = matcher
            if matcher.match(channel):
                frame = build_pmessage(pattern, channel, payload)
                for session in list(self._patterns[pattern]):
                    session.deliver(frame)
                    receivers += 1
        return receivers

    # ------------------------------------------------------- introspection
    def active_channels(self, pattern=None):
        """Channel names with at least one subscriber; optionally
        filtered by a glob (order is arbitrary, like redis)."""
        if pattern is None:
            return list(self._channels)
        matcher = compile_glob(pattern)
        return [name for name in self._channels if matcher.match(name)]

    def numsub(self, channel):
        return len(self._channels.get(channel, ()))

    def numpatterns(self):
        return len(self._patterns)


def build_message(channel, payload):
    """RESP frame: [message, channel, payload]."""
    from kagni.resp import protocolBuilder

    return protocolBuilder([b"message", channel, payload])


def build_pmessage(pattern, channel, payload):
    """RESP frame: [pmessage, pattern, channel, payload]."""
    from kagni.resp import protocolBuilder

    return protocolBuilder([b"pmessage", pattern, channel, payload])
