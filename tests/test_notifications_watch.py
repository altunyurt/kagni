"""Keyspace notifications (CONFIG SET notify-keyspace-events, event
channels and class gating) and WATCH/UNWATCH optimistic transactions.

Expected channels/event names were captured from a real redis in the
probes that shaped the implementation.
"""

import time as _wall

from kagni.commands import Commands, Session
from kagni.data import Data
from kagni.resp import RESPReader, protocolBuilder, protocolParser

from .helpers import _commands, _expect_error


def _subscriber(c, session):
    """Subscribe to both event patterns and return the captured
    (channel, message) pairs delivered so far."""
    session.outbox.clear()
    c.dispatch([b"PSUBSCRIBE", b"__keyevent@0__:*", b"__keyspace@0__:*"], session)
    frames = session.outbox
    session.outbox = []
    return frames  # (kept simple: the caller clears before each check)


def _events(c, session, clear=True):
    frames = list(session.outbox)
    if clear:
        session.outbox.clear()
    events = []
    for frame in frames:
        parsed = protocolParser(frame)
        if parsed[0] == b"pmessage":
            events.append((parsed[2], parsed[3]))
    return events


def test_config_set_and_get_validation():
    c = _commands()
    s = Session()
    assert c.dispatch([b"CONFIG", b"SET", b"notify-keyspace-events", b"AKE"], s) == b"+OK\r\n"
    reply = protocolParser(c.dispatch([b"CONFIG", b"GET", b"notify-keyspace-events"], s))
    assert reply == [b"notify-keyspace-events", b"AKE"]
    # invalid class characters are rejected with redis' wording
    err = c.dispatch([b"CONFIG", b"SET", b"notify-keyspace-events", b"KQ"], s)
    assert b"Invalid event class character" in err and b"Use 'Ag$lshzxeKEtmdn'" in err
    # other parameters are still not settable
    err = c.dispatch([b"CONFIG", b"SET", b"save", b"900 1"], s)
    assert b"Unknown option or number of arguments for CONFIG SET - 'save'" in err
    # empty value disables notifications again
    assert c.dispatch([b"CONFIG", b"SET", b"notify-keyspace-events", b""], s) == b"+OK\r\n"
    reply = protocolParser(c.dispatch([b"CONFIG", b"GET", b"notify*"], s))
    assert reply == [b"notify-keyspace-events", b""]


def test_keyspace_events_basic_set():
    c = _commands()
    sub, pub = Session(), Session()
    c.dispatch([b"CONFIG", b"SET", b"notify-keyspace-events", b"AKE"], pub)
    c.dispatch([b"PSUBSCRIBE", b"__keyevent@0__:*", b"__keyspace@0__:*"], sub)
    sub.outbox.clear()
    assert c.dispatch([b"SET", b"k", b"v"], pub) == b"+OK\r\n"
    assert _events(c, sub) == [
        (b"__keyspace@0__:k", b"set"),
        (b"__keyevent@0__:set", b"k"),
    ]
    # blocked NX writes fire nothing
    c.dispatch([b"SET", b"k", b"v2", b"NX"], pub)
    assert _events(c, sub) == []
    # counter family all reports incrby; MSET one set per key
    c.dispatch([b"INCR", b"n"], pub)
    c.dispatch([b"DECRBY", b"n", b"1"], pub)
    c.dispatch([b"MSET", b"a", b"1", b"b", b"2"], pub)
    events = _events(c, sub)
    assert (b"__keyspace@0__:n", b"incrby") in events
    assert (b"__keyevent@0__:incrby", b"n") in events
    assert events.count((b"__keyevent@0__:set", b"a")) == 1
    assert events.count((b"__keyevent@0__:set", b"b")) == 1
    # delete: only live keys fire del (missing keys nothing)
    c.dispatch([b"DEL", b"a", b"missing"], pub)
    assert _events(c, sub) == [
        (b"__keyspace@0__:a", b"del"),
        (b"__keyevent@0__:del", b"a"),
    ]
    # expiry: EXPIRE on a live key fires expire; past deadlines delete (del)
    c.dispatch([b"SETEX", b"e", b"100", b"v"], pub)
    c.dispatch([b"EXPIRE", b"e", b"50"], pub)
    events = _events(c, sub)
    assert (b"__keyevent@0__:set", b"e") in events
    assert (b"__keyevent@0__:expire", b"e") in events
    c.dispatch([b"EXPIRE", b"e", b"0"], pub)
    assert (b"__keyevent@0__:del", b"e") in _events(c, sub)
    # GETDEL and PERSIST
    c.dispatch([b"SET", b"g", b"v"], pub)
    c.dispatch([b"EXPIRE", b"g", b"100"], pub)
    c.dispatch([b"GETDEL", b"g"], pub)
    assert (b"__keyevent@0__:del", b"g") in _events(c, sub)


def test_keyspace_events_types():
    c = _commands()
    sub, pub = Session(), Session()
    c.dispatch([b"CONFIG", b"SET", b"notify-keyspace-events", b"AKE"], pub)
    c.dispatch([b"PSUBSCRIBE", b"__keyevent@0__:*"], sub)
    sub.outbox.clear()

    c.dispatch([b"RPUSH", b"l", b"a"], pub)
    assert (b"__keyevent@0__:rpush", b"l") in _events(c, sub)
    c.dispatch([b"LPUSHX", b"l", b"z"], pub)
    assert (b"__keyevent@0__:lpush", b"l") in _events(c, sub)
    c.dispatch([b"LPOP", b"l"], pub)
    events = _events(c, sub)
    assert (b"__keyevent@0__:lpop", b"l") in events
    c.dispatch([b"SADD", b"s", b"a"], pub)
    assert (b"__keyevent@0__:sadd", b"s") in _events(c, sub)
    c.dispatch([b"SADD", b"s", b"a"], pub)  # no-op
    assert _events(c, sub) == []
    c.dispatch([b"SREM", b"s", b"a"], pub)
    events = _events(c, sub)
    assert (b"__keyevent@0__:srem", b"s") in events
    assert (b"__keyevent@0__:del", b"s") in events  # emptied
    c.dispatch([b"HSET", b"h", b"f", b"v"], pub)
    c.dispatch([b"HINCRBY", b"h", b"n", b"1"], pub)
    events = _events(c, sub)
    assert (b"__keyevent@0__:hset", b"h") in events
    assert (b"__keyevent@0__:hincrby", b"h") in events
    c.dispatch([b"ZADD", b"z", b"1", b"a"], pub)
    c.dispatch([b"ZINCRBY", b"z", b"1", b"a"], pub)
    events = _events(c, sub)
    assert (b"__keyevent@0__:zadd", b"z") in events
    assert (b"__keyevent@0__:zincr", b"z") in events
    c.dispatch([b"SETBIT", b"b", b"0", b"1"], pub)
    c.dispatch([b"SETBIT", b"b", b"0", b"1"], pub)  # unchanged: nothing
    events = _events(c, sub)
    assert events.count((b"__keyevent@0__:setbit", b"b")) == 1


def test_keyspace_event_class_gating():
    c = _commands()
    sub, pub = Session(), Session()
    c.dispatch([b"CONFIG", b"SET", b"notify-keyspace-events", b"E$"], pub)
    c.dispatch([b"PSUBSCRIBE", b"__keyevent@0__:*", b"__keyspace@0__:*"], sub)
    sub.outbox.clear()
    c.dispatch([b"SET", b"k", b"v"], pub)        # string class: fires
    c.dispatch([b"RPUSH", b"l", b"a"], pub)      # list class: gated out
    events = _events(c, sub)
    assert (b"__keyevent@0__:set", b"k") in events
    assert not any(channel == b"__keyevent@0__:rpush" for channel, _ in events)
    # no K flag: keyspace channels stay silent
    assert not any(channel.startswith(b"__keyspace@0__") for channel, _ in events)


def test_expired_event_on_lazy_purge():
    c = _commands()
    pub, reader = Session(), Session()
    c.dispatch([b"CONFIG", b"SET", b"notify-keyspace-events", b"AKE"], pub)
    c.dispatch([b"PSUBSCRIBE", b"__keyevent@0__:*", b"__keyspace@0__:*"], reader)
    reader.outbox.clear()
    # plant a corpse: deadline long past, entry still stored
    c.data._storage[b"dead"] = {"value": b"x", "expires_at": 1}
    assert c.dispatch([b"GET", b"dead"], pub) == b"$-1\r\n"
    events = _events(c, reader)
    assert (b"__keyevent@0__:expired", b"dead") in events
    assert (b"__keyspace@0__:dead", b"expired") in events


def test_watch_exec_semantics():
    store = Data()
    c = Commands(data=store)
    c2 = Commands(data=store)
    a, b = Session(), Session()
    # clean transaction runs and clears the watch set
    c.dispatch([b"SET", b"k", b"1"], a)
    c.dispatch([b"WATCH", b"k"], a)
    c.dispatch([b"MULTI"], a)
    c.dispatch([b"INCR", b"k"], a)
    assert c.dispatch([b"EXEC"], a) == b"*1\r\n:2\r\n"
    assert a.watched == {}
    # a write by another connection aborts the queued transaction
    c.dispatch([b"SET", b"k", b"10"], a)
    c.dispatch([b"WATCH", b"k"], a)
    c.dispatch([b"MULTI"], a)
    c.dispatch([b"SET", b"other", b"x"], a)
    c2.dispatch([b"SET", b"k", b"20"], b)
    assert c.dispatch([b"EXEC"], a) == b"*-1\r\n"
    assert c.dispatch([b"GET", b"other"], a) == b"$-1\r\n"  # aborted
    assert c.dispatch([b"GET", b"k"], a) == b"$2\r\n20\r\n"
    # deleting and recreating with the same value still counts
    c.dispatch([b"SET", b"k", b"v"], a)
    c.dispatch([b"WATCH", b"k"], a)
    c.dispatch([b"MULTI"], a)
    c.dispatch([b"GET", b"k"], a)
    c2.dispatch([b"DEL", b"k"], b)
    c2.dispatch([b"SET", b"k", b"v"], b)
    assert c.dispatch([b"EXEC"], a) == b"*-1\r\n"
    # an expiry applied by another connection aborts too
    c.dispatch([b"SET", b"k", b"v"], a)
    c.dispatch([b"WATCH", b"k"], a)
    c.dispatch([b"MULTI"], a)
    c.dispatch([b"GET", b"k"], a)
    c2.dispatch([b"EXPIRE", b"k", b"100"], b)
    assert c.dispatch([b"EXEC"], a) == b"*-1\r\n"
    # ... and so does a TTL change on a watched expiring key
    c.dispatch([b"SET", b"k", b"v", b"EX", b"100"], a)
    c.dispatch([b"WATCH", b"k"], a)
    c.dispatch([b"MULTI"], a)
    c.dispatch([b"GET", b"k"], a)
    c2.dispatch([b"EXPIRE", b"k", b"200"], b)
    assert c.dispatch([b"EXEC"], a) == b"*-1\r\n"
    # watching a missing key: its creation aborts
    c.dispatch([b"WATCH", b"fresh"], a)
    c.dispatch([b"MULTI"], a)
    c.dispatch([b"GET", b"fresh"], a)
    c2.dispatch([b"SET", b"fresh", b"1"], b)
    assert c.dispatch([b"EXEC"], a) == b"*-1\r\n"
    # UNWATCH clears the interest; DISCARD clears it too
    c.dispatch([b"WATCH", b"fresh"], a)
    c2.dispatch([b"SET", b"fresh", b"2"], b)
    assert c.dispatch([b"UNWATCH"], a) == b"+OK\r\n"
    assert a.watched == {}
    c.dispatch([b"WATCH", b"fresh"], a)
    c.dispatch([b"MULTI"], a)
    assert c.dispatch([b"DISCARD"], a) == b"+OK\r\n"
    assert a.watched == {}
    # WATCH inside MULTI is refused at queue time
    c.dispatch([b"MULTI"], a)
    err = c.dispatch([b"WATCH", b"k"], a)
    assert err == b"-ERR WATCH inside MULTI is not allowed\r\n"
    assert c.dispatch([b"DISCARD"], a) == b"+OK\r\n"
    # arity
    assert b"wrong number of arguments" in c.dispatch([b"WATCH"], a)
