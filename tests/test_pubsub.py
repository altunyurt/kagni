"""Pub/sub: subscribe/unsubscribe grammar, the subscribed-mode gate,
PING's two-element reply, and message fan-out.  Expected frames were
captured from a real redis 7.4/8.0 in the live probes that shaped the
implementation."""

import time

from kagni.commands import Commands, Session
from kagni.data import Data
from kagni.resp import RESPReader, protocolBuilder, protocolParser

from .helpers import _commands, _expect_error


def _decode(frames):
    return [protocolParser(f) for f in frames]


def test_subscribe_confirmations_and_counts():
    c = _commands()
    s = Session()
    assert c.dispatch([b"SUBSCRIBE", b"ch1", b"ch2"], s) is None
    assert _decode(s.outbox) == [
        [b"subscribe", b"ch1", 1],
        [b"subscribe", b"ch2", 2],
    ]
    # the count spans channels and patterns together, like redis
    c.dispatch([b"PSUBSCRIBE", b"p1", b"p2"], s)
    assert _decode(s.outbox[2:]) == [
        [b"psubscribe", b"p1", 3],
        [b"psubscribe", b"p2", 4],
    ]
    # re-subscribing an existing channel confirms again without growing
    c.dispatch([b"SUBSCRIBE", b"ch1"], s)
    assert _decode(s.outbox[4:]) == [[b"subscribe", b"ch1", 4]]
    assert s.subscription_count == 4


def test_unsubscribe_bookkeeping():
    c = _commands()
    s = Session()
    c.dispatch([b"SUBSCRIBE", b"a", b"b"], s)
    s.outbox.clear()
    # named unsubscribes echo the name even when never subscribed
    c.dispatch([b"UNSUBSCRIBE", b"nope"], s)
    c.dispatch([b"UNSUBSCRIBE", b"a", b"a"], s)  # per-argument frames
    assert _decode(s.outbox) == [
        [b"unsubscribe", b"nope", 2],
        [b"unsubscribe", b"a", 1],
        [b"unsubscribe", b"a", 1],
    ]
    # bare unsubscribe clears every channel; with nothing left at all a
    # null channel is confirmed (redis shape)
    s.outbox.clear()
    c.dispatch([b"UNSUBSCRIBE"], s)
    assert _decode(s.outbox) == [[b"unsubscribe", b"b", 0]]
    c.dispatch([b"UNSUBSCRIBE"], s)
    assert _decode(s.outbox[1:]) == [[b"unsubscribe", None, 0]]
    assert not s.subscribed
    # bare unsubscribe only removes channels, patterns stay (and keep
    # the client in subscribed mode)
    s.outbox.clear()
    c.dispatch([b"PSUBSCRIBE", b"x*"], s)
    s.outbox.clear()
    c.dispatch([b"UNSUBSCRIBE"], s)
    assert _decode(s.outbox) == [[b"unsubscribe", None, 1]]
    assert s.subscribed
    c.dispatch([b"PUNSUBSCRIBE"], s)
    assert not s.subscribed


def test_subscribed_mode_gate_and_ping():
    c = _commands()
    s = Session()
    c.dispatch([b"SUBSCRIBE", b"ch"], s)
    s.outbox.clear()

    def gate(*tokens):
        return c.dispatch(list(tokens) + ([b"ch"] if tokens[0] == b"SUBSCRIBE" else []), s)

    err = c.dispatch([b"GET", b"k"], s)
    assert b"Can't execute 'get': only (P|S)SUBSCRIBE" in err
    assert b"client|setname" in c.dispatch([b"CLIENT", b"SETNAME", b"x"], s)
    assert b"config|get" in c.dispatch([b"CONFIG", b"GET", b"maxmemory"], s)
    assert b"command|count" in c.dispatch([b"COMMAND", b"COUNT"], s)
    assert b"pubsub|numpat" in c.dispatch([b"PUBSUB", b"NUMPAT"], s)
    assert b"Can't execute 'publish'" in c.dispatch([b"PUBLISH", b"ch", b"x"], s)
    assert b"Can't execute 'multi'" in c.dispatch([b"MULTI"], s)
    assert b"Can't execute 'discard'" in c.dispatch([b"DISCARD"], s)
    exec_err = c.dispatch([b"EXEC"], s)
    assert exec_err.startswith(b"-EXECABORT Transaction discarded")
    # unknown commands keep their own error, not the gate
    assert b"unknown command 'NOSUCH'" in c.dispatch([b"NOSUCH"], s)
    # PING answers a two-element array while subscribed
    assert protocolParser(c.dispatch([b"PING"], s)) == [b"pong", b""]
    assert protocolParser(c.dispatch([b"PING", b"pp"], s)) == [b"pong", b"pp"]
    # leaving subscribed mode restores normal replies
    c.dispatch([b"UNSUBSCRIBE"], s)
    s.outbox.clear()
    assert c.dispatch([b"PING"], s) == b"+PONG\r\n"
    assert c.dispatch([b"GET", b"k"], s) == b"$-1\r\n"


def test_publish_delivery_and_receiver_count():
    c = _commands()
    sub = Session()
    sub2 = Session()
    c.dispatch([b"SUBSCRIBE", b"news"], sub)
    c.dispatch([b"PSUBSCRIBE", b"n*"], sub2)
    pub = Session()
    # one channel delivery + one pattern delivery: receivers counts
    # delivered frames, like redis
    sub.outbox.clear()
    sub2.outbox.clear()
    reply = c.dispatch([b"PUBLISH", b"news", b"hello"], pub)
    assert reply == b":2\r\n"
    frames = _decode(sub.outbox) + _decode(sub2.outbox)
    assert frames == [
        [b"message", b"news", b"hello"],
        [b"pmessage", b"n*", b"news", b"hello"],
    ]
    # no subscribers at all
    assert c.dispatch([b"PUBLISH", b"void", b"x"], pub) == b":0\r\n"
    # payloads are binary-safe
    sub.outbox.clear()
    payload = b"line1\r\nline2\x00\xff"
    c.dispatch([b"PUBLISH", b"news", payload], pub)
    assert _decode(sub.outbox) == [[b"message", b"news", payload]]


def test_pubsub_introspection_and_errors():
    c = _commands()
    s = Session()
    pub = Session()
    c.dispatch([b"SUBSCRIBE", b"a", b"b"], s)
    c.dispatch([b"PSUBSCRIBE", b"p*"], s)
    assert sorted(protocolParser(c.dispatch([b"PUBSUB", b"CHANNELS"], pub))) == [
        b"a", b"b"
    ]
    assert sorted(protocolParser(c.dispatch([b"PUBSUB", b"CHANNELS", b"a*"], pub))) == [b"a"]
    assert protocolParser(c.dispatch([b"PUBSUB", b"NUMSUB", b"a", b"nope", b"b"], pub)) == [
        b"a", 1, b"nope", 0, b"b", 1
    ]
    assert protocolParser(c.dispatch([b"PUBSUB", b"NUMPAT"], pub)) == 1
    assert protocolParser(c.dispatch([b"PUBSUB", b"NUMSUB"], pub)) == []
    err = c.dispatch([b"PUBSUB", b"BOGUS"], pub)
    assert b"unknown subcommand 'BOGUS'. Try PUBSUB HELP." in err
    assert b"wrong number of arguments" in c.dispatch([b"PUBSUB"], pub)
    assert b"wrong number of arguments" in c.dispatch([b"SUBSCRIBE"])
    # a disconnected session disappears from the hub
    c.hub.remove_session(s)
    assert c.dispatch([b"PUBSUB", b"NUMSUB", b"a"], pub) == b"*2\r\n$1\r\na\r\n:0\r\n"


def test_subscribe_inside_multi_exec():
    c = _commands()
    s = Session()
    assert c.dispatch([b"MULTI"], s) == b"+OK\r\n"
    assert c.dispatch([b"SUBSCRIBE", b"m1"], s) == b"+QUEUED\r\n"
    # the confirmation is nested inside the EXEC array, like redis
    exec_reply = c.dispatch([b"EXEC"], s)
    assert exec_reply == b"*1\r\n" + protocolBuilder([b"subscribe", b"m1", 1])
    assert s.subscribed
    assert protocolParser(c.dispatch([b"PING"], s)) == [b"pong", b""]
    c.dispatch([b"UNSUBSCRIBE"], s)


# ------------------------------------------------------------ live server
def test_pubsub_over_the_wire(kagni_server):
    import socket

    def conn():
        s = socket.create_connection((kagni_server.host, kagni_server.port), timeout=2)
        s.settimeout(0.2)
        return s, RESPReader(engine="python")

    def send(s, *args):
        s.sendall(b"*%d\r\n" % len(args) + b"".join(b"$%d\r\n%s\r\n" % (len(a), a) for a in args))

    def pump(s, r, until=None):
        got = []
        deadline = time.monotonic() + (until if until else 0.2)
        while time.monotonic() < deadline:
            try:
                chunk = s.recv(65536)
            except socket.timeout:
                continue
            if not chunk:
                break
            for m in r.feed(chunk):
                if m is not None:
                    got.append(m)
        return got

    sub, sub_r = conn()
    pub, pub_r = conn()
    try:
        send(sub, b"SUBSCRIBE", b"wire")
        assert pump(sub, sub_r) == [[b"subscribe", b"wire", 1]]
        send(pub, b"PUBLISH", b"wire", b"over-tcp")
        assert pump(pub, pub_r, until=0.5) == [1]
        assert pump(sub, sub_r, until=0.5) == [[b"message", b"wire", b"over-tcp"]]
        # a closed subscriber leaves the hub
        send(sub, b"UNSUBSCRIBE", b"wire")
        pump(sub, sub_r)
        sub.close()
        for _ in range(10):
            send(pub, b"PUBLISH", b"wire", b"x")
            if pump(pub, pub_r, until=0.3) == [0]:
                break
        else:
            raise AssertionError("closed subscriber still in the hub")
        # gate over the wire (fresh subscriber connection)
        sub2, sub2_r = conn()
        try:
            send(sub2, b"SUBSCRIBE", b"g")
            assert pump(sub2, sub2_r) == [[b"subscribe", b"g", 1]]
            send(sub2, b"GET", b"k")
            assert b"Can't execute 'get'" in pump(sub2, sub2_r)[0]
            send(sub2, b"PING")
            assert pump(sub2, sub2_r) == [[b"pong", b""]]
        finally:
            sub2.close()
    finally:
        for s in (sub, pub):
            try:
                s.close()
            except OSError:
                pass
