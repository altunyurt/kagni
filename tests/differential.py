#!/usr/bin/env python
"""Differential battery: run the same command stream against a real redis
and a freshly spawned kagni; every reply must be byte-identical.

Not collected by pytest (no test_ prefix): it needs a real redis nearby.

    redis-server --port 6379 &     # or point KAGNI_DIFF_REDIS at one
    python tests/differential.py   # exits 1 on any reply mismatch

Redis address: KAGNI_DIFF_REDIS=host:port (default 127.0.0.1:6379).  The
stream mirrors the redis 7.4 semantics kagni targets (verified against
8.0.2, whose behaviour for this subset is identical).
"""
import os
import re
import socket

from kagni.resp import RESPReader
import subprocess
import sys
import time


def redis_addr():
    addr = os.environ.get("KAGNI_DIFF_REDIS", "127.0.0.1:6379")
    host, _, port = addr.partition(":")
    return host, int(port or 6379)


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


REDIS = redis_addr()
KAGNI_PORT = free_port()

BATCHES = [
    [(b"FLUSHALL",)],
    # ---- collection scans
    [(b"HSET", b"h", b"f1", b"v1", b"f2", b"v2", b"other", b"x"),
     (b"HSCAN", b"h", b"0"), (b"HSCAN", b"h", b"0", b"MATCH", b"f*"),
     (b"HSCAN", b"h", b"0", b"COUNT", b"1"), (b"HSCAN", b"h", b"7"),
     (b"HSCAN", b"h", b"7", b"MATCH", b"nope*"), (b"HSCAN", b"h", b"0", b"MATCH", b"nomatch"),
     (b"HSCAN", b"noh", b"0"), (b"HSCAN", b"noh", b"5", b"MATCH", b"f*"),
     (b"HSCAN", b"h", b"abc"), (b"HSCAN", b"h", b"-1"),
     (b"HSCAN", b"h", b"0", b"COUNT", b"0"), (b"HSCAN", b"h", b"0", b"COUNT", b"-2"),
     (b"HSCAN", b"h", b"0", b"COUNT", b"x"), (b"HSCAN", b"h", b"0", b"BOGUS", b"1"),
     (b"HSCAN", b"h", b"0", b"MATCH"), (b"HSCAN", b"h", b"0", b"TYPE", b"hash"),
     (b"SADD", b"s", b"aa", b"ab", b"bb"), (b"SSCAN", b"s", b"0"),
     (b"SSCAN", b"s", b"0", b"MATCH", b"a*"), (b"SSCAN", b"s", b"0", b"MATCH", b"a*", b"COUNT", b"1"),
     (b"SSCAN", b"nos", b"0"), (b"SSCAN", b"s", b"3"), (b"SSCAN", b"s", b"abc"),
     (b"ZADD", b"z", b"1", b"m1", b"2", b"m2", b"3", b"other"),
     (b"ZSCAN", b"z", b"0"), (b"ZSCAN", b"z", b"0", b"MATCH", b"m*"),
     (b"ZSCAN", b"z", b"0", b"MATCH", b"m*", b"COUNT", b"2"),
     (b"ZSCAN", b"noz", b"0"), (b"ZSCAN", b"z", b"0", b"MATCH", b"x*"),
     (b"ZSCAN", b"z", b"0", b"MATCH"), (b"ZSCAN", b"z", b"9"),
     (b"HSET", b"str", b"f", b"v"), (b"HSCAN", b"str", b"0"),
     (b"SSCAN", b"str", b"0"), (b"ZSCAN", b"str", b"0")],
    # ---- zadd options / replies
    [(b"ZADD", b"k", b"1", b"a"), (b"ZADD", b"k", b"NX", b"2", b"a"),
     (b"ZADD", b"k", b"XX", b"3", b"a"), (b"ZADD", b"k", b"XX", b"9", b"nope"),
     (b"ZADD", b"k2", b"XX", b"1", b"a"), (b"EXISTS", b"k2"),
     (b"ZADD", b"k", b"GT", b"5", b"a"), (b"ZADD", b"k", b"CH", b"1", b"a", b"7", b"b"),
     (b"ZADD", b"k", b"NX", b"GT", b"1", b"a"), (b"ZADD", b"k", b"GT", b"LT", b"1", b"a"),
     (b"ZADD", b"k", b"NX", b"XX", b"1", b"a"),
     (b"ZADD", b"k", b"INCR", b"5", b"a"), (b"ZADD", b"k", b"INCR", b"NX", b"5", b"a"),
     (b"ZADD", b"k", b"INCR", b"1", b"a", b"2", b"b"),
     (b"ZADD", b"k", b"1", b"a", b"2", b"a"), (b"ZADD", b"k", b"CH", b"1", b"a", b"2", b"a"),
     (b"ZADD", b"k", b"badscore", b"a"), (b"ZADD", b"k", b"nan", b"a"),
     (b"ZADD", b"k", b"1", b"a", b"2"), (b"ZADD", b"k", b"1"),
     (b"ZADD", b"ki", b"inf", b"a"), (b"ZADD", b"ki", b"-inf", b"b"),
     (b"ZINCRBY", b"ki", b"inf", b"a"), (b"ZINCRBY", b"ki", b"-inf", b"a"),
     (b"ZINCRBY", b"nokey", b"1.5", b"m"), (b"ZSCORE", b"nokey", b"m"),
     (b"ZADD", b"d", b"1", b"a", b"2", b"a"), (b"ZRANGE", b"d", b"0", b"-1", b"WITHSCORES"),
     (b"ZADD", b"d", b"CH", b"3", b"a", b"4", b"a"), (b"ZADD", b"d", b"CH", b"3", b"a", b"3", b"b"),
     (b"ZADD", b"g", b"GT", b"5", b"newm"), (b"ZSCORE", b"g", b"newm"),
     (b"ZADD", b"g3", b"1", b"m"), (b"ZADD", b"g3", b"INCR", b"GT", b"5", b"m"),
     (b"ZADD", b"g3", b"INCR", b"LT", b"2", b"m"), (b"ZSCORE", b"g3", b"m"),
     (b"ZADD", b"g4", b"INCR", b"GT", b"-5", b"brandnew"),
     (b"ZADD", b"g5", b"INCR", b"XX", b"5", b"brandnew"), (b"EXISTS", b"g5")],
    # ---- scores/formatting/ranks
    [(b"ZADD", b"fm", b"10.5", b"x"), (b"ZSCORE", b"fm", b"x"),
     (b"ZADD", b"fm", b"1e300", b"y"), (b"ZSCORE", b"fm", b"y"),
     (b"ZADD", b"fm", b"-0", b"z"), (b"ZSCORE", b"fm", b"z"),
     (b"ZADD", b"fm", b"3.0", b"w"), (b"ZSCORE", b"fm", b"w"),
     (b"ZADD", b"fm", b"0.1", b"u"), (b"ZINCRBY", b"fm", b"0.2", b"u"), (b"ZSCORE", b"fm", b"u"),
     (b"ZADD", b"r", b"1", b"a", b"2", b"b", b"3", b"c"),
     (b"ZRANK", b"r", b"b"), (b"ZRANK", b"r", b"b", b"WITHSCORE"),
     (b"ZRANK", b"r", b"nope"), (b"ZRANK", b"r", b"nope", b"WITHSCORE"),
     (b"ZREVRANK", b"r", b"a"), (b"ZREVRANK", b"r", b"a", b"WITHSCORE"),
     (b"ZSCORE", b"r", b"nope"), (b"ZSCORE", b"nokey", b"nope"),
     (b"ZMSCORE", b"r", b"a", b"nope", b"c"), (b"ZMSCORE", b"nokey2", b"a", b"b"),
     (b"ZCARD", b"r"), (b"ZCARD", b"nokey2")],
    # ---- unified zrange grammar
    [(b"ZRANGE", b"r", b"0", b"-1"), (b"ZRANGE", b"r", b"0", b"-1", b"WITHSCORES"),
     (b"ZRANGE", b"r", b"0", b"-1", b"REV"), (b"ZRANGE", b"r", b"1", b"2"),
     (b"ZRANGE", b"r", b"-2", b"-1"), (b"ZRANGE", b"r", b"5", b"10"),
     (b"ZRANGE", b"r", b"(1", b"+inf", b"BYSCORE"), (b"ZRANGE", b"r", b"-inf", b"2", b"BYSCORE", b"WITHSCORES"),
     (b"ZRANGE", b"r", b"(1", b"(3", b"BYSCORE"), (b"ZRANGE", b"r", b"3", b"1", b"BYSCORE", b"REV"),
     (b"ZRANGE", b"r", b"3", b"1", b"BYSCORE", b"REV", b"LIMIT", b"1", b"1"),
     (b"ZRANGE", b"r", b"0", b"-1", b"LIMIT", b"0", b"1"),
     (b"ZRANGE", b"r", b"-", b"+", b"BYLEX"), (b"ZRANGE", b"r", b"[b", b"[c", b"BYLEX"),
     (b"ZRANGE", b"r", b"[b", b"[c", b"BYLEX", b"REV"),
     (b"ZRANGE", b"r", b"-", b"+", b"BYLEX", b"WITHSCORES"),
     (b"ZRANGE", b"r", b"0", b"1", b"BYLEX"), (b"ZRANGE", b"r", b"0", b"1", b"BYSCORE"),
     (b"ZRANGE", b"r", b"0", b"-1", b"REV", b"REV"),
     (b"ZRANGE", b"r", b"0", b"-1", b"WITHSCORES", b"WITHSCORES"),
     (b"ZRANGE", b"r", b"0", b"-1", b"BYSCORE", b"BYLEX"),
     (b"ZRANGE", b"r", b"0", b"1", b"WITHSCORES", b"BYSCORE"),
     (b"ZRANGE", b"r", b"0", b"1", b"LIMIT", b"0", b"5", b"BYSCORE"),
     (b"ZRANGE", b"r", b"x", b"1"), (b"ZRANGE", b"r", b"x", b"1", b"BYSCORE"),
     (b"ZRANGE", b"nokey3", b"x", b"1", b"BYSCORE"),
     (b"ZRANGE", b"r", b"1", b"3", b"BYSCORE", b"LIMIT", b"-1", b"1"),
     (b"ZRANGE", b"r", b"1", b"3", b"BYSCORE", b"LIMIT", b"1", b"-1")],
    # ---- legacy wrappers
    [(b"ZRANGEBYSCORE", b"r", b"1", b"2", b"WITHSCORES"),
     (b"ZREVRANGEBYSCORE", b"r", b"2", b"1"),
     (b"ZREVRANGEBYSCORE", b"r", b"+inf", b"-inf", b"WITHSCORES", b"LIMIT", b"1", b"1"),
     (b"ZRANGEBYSCORE", b"r", b"1", b"3", b"LIMIT", b"-5", b"1"),
     (b"ZRANGEBYSCORE", b"r", b"1", b"3", b"LIMIT", b"0", b"-1"),
     (b"ZRANGEBYSCORE", b"r", b"abc", b"+inf"), (b"ZREVRANGE", b"r", b"0", b"-1"),
     (b"ZREVRANGE", b"r", b"0", b"-1", b"WITHSCORES"), (b"ZREVRANGE", b"r", b"0", b"1"),
     (b"ZCOUNT", b"r", b"-inf", b"2"), (b"ZCOUNT", b"r", b"(2", b"+inf"),
     (b"ZCOUNT", b"r", b"abc", b"+inf"), (b"ZCOUNT", b"nokey3", b"-inf", b"+inf"),
     (b"ZADD", b"lx", b"0", b"a", b"0", b"b", b"0", b"c", b"0", b"d"),
     (b"ZRANGEBYLEX", b"lx", b"-", b"+"), (b"ZRANGEBYLEX", b"lx", b"[b", b"(d"),
     (b"ZRANGEBYLEX", b"lx", b"(a", b"+", b"LIMIT", b"1", b"2"),
     (b"ZREVRANGEBYLEX", b"lx", b"+", b"-", b"LIMIT", b"1", b"2"),
     (b"ZREVRANGEBYLEX", b"lx", b"[c", b"[a"),
     (b"ZLEXCOUNT", b"lx", b"[b", b"+"), (b"ZLEXCOUNT", b"lx", b"(a", b"(d"),
     (b"ZLEXCOUNT", b"nokey3", b"-", b"+"),
     (b"ZRANGEBYLEX", b"lx", b"x", b"+"), (b"ZRANGEBYLEX", b"lx", b"-", b"y"),
     (b"ZRANGEBYLEX", b"lx", b"[", b"+"), (b"ZRANGEBYLEX", b"lx", b"-", b"-"),
     (b"ZREVRANGEBYLEX", b"lx", b"-", b"+"), (b"ZRANGEBYLEX", b"lx", b"(a", b"[a")],
    # ---- removals / pops / empty deletion
    [(b"ZREM", b"r", b"a"), (b"ZREM", b"r", b"nope"), (b"ZRANGE", b"r", b"0", b"-1"),
     (b"ZADD", b"rr", b"1", b"a", b"2", b"b", b"3", b"c", b"4", b"d"),
     (b"ZREMRANGEBYRANK", b"rr", b"0", b"1"), (b"ZRANGE", b"rr", b"0", b"-1"),
     (b"ZREMRANGEBYSCORE", b"rr", b"4", b"4"), (b"ZRANGE", b"rr", b"0", b"-1"),
     (b"ZREMRANGEBYLEX", b"lx", b"[a", b"[b"), (b"ZRANGEBYLEX", b"lx", b"-", b"+"),
     (b"ZREMRANGEBYRANK", b"lx", b"0", b"0"), (b"ZREMRANGEBYSCORE", b"lx", b"-inf", b"0"),
     (b"EXISTS", b"lx"), (b"ZREMRANGEBYRANK", b"nokey3", b"0", b"-1"),
     (b"ZREMRANGEBYSCORE", b"nokey3", b"0", b"1"), (b"ZREMRANGEBYLEX", b"nokey3", b"-", b"+"),
     (b"ZPOPMIN", b"fm"), (b"ZPOPMIN", b"fm", b"2"), (b"ZPOPMIN", b"fm", b"-1"),
     (b"ZPOPMIN", b"fm", b"0"), (b"ZPOPMAX", b"fm", b"1"),
     (b"ZPOPMAX", b"nokey3"), (b"ZPOPMAX", b"nokey3", b"2"), (b"ZPOPMAX", b"nokey3", b"0"),
     (b"ZADD", b"one", b"9", b"x"), (b"ZPOPMIN", b"one"), (b"EXISTS", b"one"),
     (b"ZADD", b"one2", b"9", b"x"), (b"ZPOPMAX", b"one2", b"5"), (b"EXISTS", b"one2"),
     (b"ZPOPMIN", b"r", b"5"), (b"EXISTS", b"r")],
    # ---- zrandmember
    [(b"ZRANDMEMBER", b"rr"), (b"ZRANDMEMBER", b"rr", b"0"), (b"ZRANDMEMBER", b"rr", b"2"),
     (b"ZRANDMEMBER", b"rr", b"-3"), (b"ZRANDMEMBER", b"rr", b"5"),
     (b"ZRANDMEMBER", b"nokey3"), (b"ZRANDMEMBER", b"nokey3", b"2"),
     (b"ZRANDMEMBER", b"nokey3", b"-2", b"WITHSCORES"),
     (b"ZRANDMEMBER", b"rr", b"1", b"WITHSCORES"), (b"ZRANDMEMBER", b"rr", b"WITHSCORES"),
     (b"ZRANDMEMBER", b"rr", b"2", b"BOGUS")],
    # ---- store ops
    [(b"ZADD", b"z1", b"1", b"a", b"2", b"b", b"3", b"c"), (b"ZADD", b"z2", b"2", b"b", b"3", b"c", b"4", b"d"),
     (b"ZUNIONSTORE", b"u", b"2", b"z1", b"z2"), (b"ZRANGE", b"u", b"0", b"-1", b"WITHSCORES"),
     (b"ZUNIONSTORE", b"u2", b"2", b"z1", b"z2", b"WEIGHTS", b"2", b"3", b"AGGREGATE", b"MIN"),
     (b"ZRANGE", b"u2", b"0", b"-1", b"WITHSCORES"),
     (b"ZINTERSTORE", b"i1", b"2", b"z1", b"z2"), (b"ZRANGE", b"i1", b"0", b"-1", b"WITHSCORES"),
     (b"ZDIFFSTORE", b"df", b"2", b"z1", b"z2"), (b"ZRANGE", b"df", b"0", b"-1", b"WITHSCORES"),
     (b"ZUNION", b"2", b"z1", b"z2", b"WITHSCORES"), (b"ZINTER", b"2", b"z1", b"z2"),
     (b"ZDIFF", b"2", b"z1", b"z2"), (b"ZDIFF", b"1", b"z1", b"WITHSCORES"),
     (b"ZUNIONSTORE", b"u3", b"0", b"z1"), (b"ZUNIONSTORE", b"u3", b"3", b"z1", b"z2"),
     (b"ZUNIONSTORE", b"u3", b"2", b"z1", b"z2", b"WEIGHTS", b"1"),
     (b"ZUNIONSTORE", b"u3", b"2", b"z1", b"z2", b"AGGREGATE", b"AVG"),
     (b"ZUNIONSTORE", b"u3", b"2", b"z1", b"z2", b"WEIGHTS", b"x", b"1"),
     (b"ZUNION", b"2", b"z1", b"z2", b"BOGUS"), (b"ZDIFFSTORE", b"d2", b"0", b"z1"),
     (b"ZDIFFSTORE", b"d2", b"1", b"z1", b"WEIGHTS", b"2"),
     (b"ZDIFFSTORE", b"d2", b"2", b"z1", b"z2", b"WITHSCORES"),
     (b"ZUNIONSTORE", b"empty", b"2", b"z1", b"z1"), (b"EXISTS", b"empty"),
     (b"ZUNIONSTORE", b"z1", b"1", b"z1", b"WEIGHTS", b"2"), (b"ZRANGE", b"z1", b"0", b"-1", b"WITHSCORES"),
     (b"ZUNIONSTORE", b"nn", b"2", b"z1", b"missing"), (b"ZRANGE", b"nn", b"0", b"-1"),
     (b"ZADD", b"wi", b"inf", b"x"), (b"ZUNIONSTORE", b"wz", b"1", b"wi", b"WEIGHTS", b"0"),
     (b"ZRANGE", b"wz", b"0", b"-1", b"WITHSCORES"),
     (b"ZADD", b"n1", b"inf", b"m"), (b"ZADD", b"n2", b"-inf", b"m"),
     (b"ZUNIONSTORE", b"ns", b"2", b"n1", b"n2"), (b"ZRANGE", b"ns", b"0", b"-1", b"WITHSCORES")],
    # ---- wrongtype / keyspace
    [(b"SET", b"str", b"x"), (b"ZADD", b"str", b"1", b"a"), (b"ZRANGE", b"str", b"0", b"-1"),
     (b"ZSCORE", b"str", b"a"), (b"ZPOPMIN", b"str"), (b"ZUNIONSTORE", b"u9", b"1", b"str"),
     (b"ZRANK", b"str", b"a"), (b"ZINCRBY", b"str", b"1", b"m"), (b"ZREM", b"str", b"m"),
     (b"ZCOUNT", b"str", b"-inf", b"+inf"), (b"ZRANGEBYLEX", b"str", b"-", b"+"),
     (b"TYPE", b"z1"), (b"TYPE", b"str")],
    # ---- hash family
    [(b"DEL", b"h"), (b"HSET", b"h", b"f1", b"v1", b"f2", b"v2"), (b"HGETALL", b"h"),
     (b"HSET", b"h", b"f3"), (b"HSET", b"h"), (b"HSET", b"h", b"f", b"v", b"g"),
     (b"HSET", b"h", b"f1", b"x", b"f2", b"y"), (b"HLEN", b"h"),
     (b"HMGET", b"h", b"f1", b"nope", b"f2"), (b"HMGET", b"noh", b"a", b"b"),
     (b"HMGET", b"h"), (b"HKEYS", b"h"), (b"HVALS", b"h"), (b"HKEYS", b"noh"), (b"HVALS", b"noh"),
     (b"HLEN", b"noh"), (b"HINCRBY", b"h", b"cnt", b"5"), (b"HINCRBY", b"h", b"cnt", b"-2"),
     (b"HSET", b"h", b"txt", b"abc"), (b"HINCRBY", b"h", b"txt", b"1"),
     (b"HINCRBY", b"h", b"big", b"9223372036854775807"), (b"HINCRBY", b"h", b"big", b"1"),
     (b"HINCRBY", b"h", b"f1", b"x"), (b"HINCRBY", b"noh", b"c", b"1"),
     (b"HINCRBY", b"str", b"c", b"1"), (b"HSET", b"str", b"c", b"1"),
     (b"HDEL", b"h", b"f1", b"f2", b"f3"), (b"HGETALL", b"h")],
    # ---- expire family / echo / info
    [(b"SET", b"ek", b"v"), (b"PEXPIRE", b"ek", b"100000"), (b"PTTL", b"ek"),
     (b"EXPIREAT", b"ek", b"1"), (b"EXISTS", b"ek"),
     (b"SET", b"ek2", b"v"), (b"EXPIREAT", b"ek2", b"1"), (b"EXISTS", b"ek2"),
     (b"PEXPIRE", b"ek3", b"0"), (b"EXISTS", b"ek3"),
     (b"PEXPIRE", b"ek2", b"-5"), (b"EXISTS", b"ek2"),
     (b"SET", b"pt", b"v"), (b"PEXPIRE", b"pt", b"1500"), (b"PTTL", b"pt"),
     (b"PEXPIRE", b"ek", b"x"), (b"PTTL", b"nokey9"), (b"TTL", b"nokey9"),
     (b"ECHO", b"hello world"), (b"ECHO", b""),
     (b"INFO", b"nosuchsection"), (b"INFO", b"keyspace")],
]


def ask(host, port, cmds):
    s = socket.create_connection((host, port), timeout=3)
    with s:
        s.settimeout(5)
        for c in cmds:
            s.sendall(b"*%d\r\n" % len(c) + b"".join(b"$%d\r\n%s\r\n" % (len(a), a) for a in c))
        out = b""
        try:
            while True:
                chunk = s.recv(65536)
                if not chunk:
                    break
                out += chunk
        except socket.timeout:
            pass
    return out


def _frame_end(buf, pos):
    """Position right after the RESP value starting at *pos*, or None
    when the buffer ends mid-frame."""
    marker = buf[pos:pos + 1]
    e = buf.index(b"\r\n", pos)
    line = buf[pos + 1:e]
    if marker in (b"+", b"-", b":"):
        return e + 2
    if marker == b"$":
        n = int(line)
        return e + 2 if n < 0 else e + 2 + n + 2
    if marker == b"*":
        n = int(line)
        if n < 0:
            return e + 2
        p = e + 2
        for _ in range(n):
            p = _frame_end(buf, p)
            if p is None:
                return None
        return p
    return None  # not a reply frame (should not happen server-side)



def _decode(frame):
    """Decode one reply frame with the pure-python parser, so error
    frames come back as bytes (hiredis wraps them in objects whose
    equality is identity-based)."""
    reader = RESPReader(engine="python")
    return reader.feed(frame)[0]


def _scan_sorted(cmd, value):
    """[cursor, items] with the items sorted (HSCAN fields keep their
    values attached); non-scan replies pass through unchanged."""
    if not isinstance(value, list) or len(value) != 2 or not isinstance(
        value[1], list
    ):
        return value
    items = value[1]
    if cmd == b"HSCAN":
        pairs = sorted(zip(items[::2], items[1::2]))
        return [value[0], [b for pair in pairs for b in pair]]
    if cmd == b"SSCAN":
        return [value[0], sorted(items)]
    return value


def split_frames(out):
    """Raw wire frames of a reply stream (nested arrays included)."""
    frames = []
    pos = 0
    while pos < len(out):
        end = _frame_end(out, pos)
        if end is None:
            break
        frames.append(out[pos:end])
        pos = end
    return frames


def main():
    try:
        probe = socket.create_connection(REDIS, timeout=2)
        probe.close()
    except OSError:
        print("no redis at %s:%s - start one or set KAGNI_DIFF_REDIS; skipping"
              % REDIS)
        return 0
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    kagni = subprocess.Popen(
        [sys.executable, "-m", "kagni", "--port", str(KAGNI_PORT), "--db", ":memory:"],
        cwd=repo,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1.0)
    mismatches = 0
    try:
        for bi, batch in enumerate(BATCHES):
            real = split_frames(ask(*REDIS, batch))
            ours = split_frames(ask("127.0.0.1", KAGNI_PORT, batch))
            # INFO keyspace: avg_ttl is a decaying cron sample in redis
            # (timing-dependent) and subexpiry is an 8.0-only field; kagni
            # reports the exact average, so compare the rest of the line
            # INFO keyspace: avg_ttl is a decaying cron sample in redis
            # (timing-dependent) and subexpiry is an 8.0-only field, so
            # drop both tokens and compare bulk payloads without their
            # $length headers
            if b"# Keyspace" in b"".join(real):
                real = [re.sub(rb"avg_ttl=\d+,subexpiry=\d+", b"avg_ttl=X", f) for f in real]
                ours = [re.sub(rb"avg_ttl=\d+", b"avg_ttl=X", f) for f in ours]
            real = [re.sub(rb"^\$\d+\r\n", b"", f) for f in real]
            ours = [re.sub(rb"^\$\d+\r\n", b"", f) for f in ours]
            # HSCAN/SSCAN item order is iteration order on both sides
            # (redis makes no promise), so compare those replies as
            # sorted collections
            normalized = any(
                cmd[0] in (b"HSCAN", b"SSCAN") for cmd in batch
            )
            if normalized:
                real = [
                    _scan_sorted(cmd[0], _decode(f))
                    for cmd, f in zip(batch, real)
                ]
                ours = [
                    _scan_sorted(cmd[0], _decode(f))
                    for cmd, f in zip(batch, ours)
                ]
            if real != ours:
                mismatches += 1
                print("== batch %d mismatch" % bi)
                for c, r, o in zip(batch, real, ours):
                    if r != o:
                        print("  %-72s redis: %-60s kagni: %s" % (b" ".join(c)[:72], r, o))
        print("batches: %d, mismatching: %d" % (len(BATCHES), mismatches))
    finally:
        kagni.terminate()
        try:
            kagni.wait(timeout=5)
        except subprocess.TimeoutExpired:
            kagni.kill()
            kagni.wait(timeout=5)
    return 1 if mismatches else 0


if __name__ == "__main__":
    sys.exit(main())
