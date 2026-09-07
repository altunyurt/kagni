#!/usr/bin/env python
"""Multi-connection differential battery: drives identical scenarios -
pub/sub fan-out, keyspace notifications, WATCH/EXEC - against a real
redis and a freshly spawned kagni, comparing every frame byte-for-byte.

Not collected by pytest (no test_ prefix): it needs a real redis.
    KAGNI_DIFF_REDIS=host:port python tests/differential_multi.py

Each scenario is a script of (connection, [commands...]) steps; after
every step all connections are drained until quiet and the frames are
appended to that connection's transcript.  At the end the transcripts
must be identical.
"""

import os
import socket
import subprocess
import sys
import time

from kagni.resp import RESPReader

REDIS = os.environ.get("KAGNI_DIFF_REDIS", "127.0.0.1:6379").split(":")
REDIS_HOST, REDIS_PORT = REDIS[0], int(REDIS[1])


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class Wire:
    """A connection with an incremental reader; frames accumulate in
    the transcript handed to the comparison."""

    def __init__(self, host, port):
        self.sock = socket.create_connection((host, port), timeout=3)
        self.sock.settimeout(0.15)
        self.reader = RESPReader(engine="python")
        self.transcript = []

    def send(self, *args):
        self.sock.sendall(
            b"*%d\r\n" % len(args)
            + b"".join(b"$%d\r\n%s\r\n" % (len(a), a) for a in args)
        )

    def drain(self):
        try:
            while True:
                chunk = self.sock.recv(65536)
                if not chunk:
                    break
                for message in self.reader.feed(chunk):
                    if message is not None:
                        self.transcript.append(message)
        except socket.timeout:
            pass

    def close(self):
        self.sock.close()


def run(host, port):
    conns = {}

    def wire(name):
        if name not in conns:
            conns[name] = Wire(host, port)
        return conns[name]

    def step(name, *commands):
        for command in commands:
            if not isinstance(command, tuple):
                command = (command,)  # tolerate a bare bytes token
            wire(name).send(*command)
        for conn in conns.values():
            conn.drain()

    # start from a clean slate on both servers (kagni is fresh, redis
    # accumulates across runs)
    step("pub", b"FLUSHALL")
    step("pub", (b"CONFIG", b"SET", b"notify-keyspace-events", b""))
    step("pub", (b"CONFIG", b"GET", b"notify-keyspace-events"))

    # ------------------------------------------------------------ pub/sub
    step("sub", (b"SUBSCRIBE", b"ch1", b"ch2"))
    step("sub", (b"PSUBSCRIBE", b"p*"))
    step("pub", (b"PUBSUB", b"NUMSUB", b"ch1", b"ch2", b"nope"))
    step("pub", (b"PUBSUB", b"NUMPAT"))
    step("pub", (b"PUBLISH", b"ch1", b"hello-\r\nbinary"))
    step("pub", (b"PUBLISH", b"pX", b"patterned"))
    step("pub", (b"PUBLISH", b"void", b"x"))
    step("sub", (b"SUBSCRIBE", b"ch1"))  # duplicate
    step("sub", (b"UNSUBSCRIBE", b"never", b"ch1"))
    step("gate", (b"SUBSCRIBE", b"gz"))
    step("gate", (b"GET", b"k"))               # gated
    step("gate", (b"PUBSUB", b"NUMPAT"))       # gated, subcommand label
    step("gate", (b"CLIENT", b"SETNAME", b"x"))
    step("gate", (b"COMMAND", b"COUNT"))
    step("gate", (b"MULTI"))                   # gated
    step("gate", (b"EXEC"))                    # EXECABORT shape
    step("gate", (b"DISCARD"))
    step("gate", (b"NOSUCHCMD"))               # unknown keeps own error
    step("gate", (b"PING"))
    step("gate", (b"PING", b"pp"))
    step("gate", (b"UNSUBSCRIBE", b"gz"))
    step("gate", (b"PING"))
    step("gate", (b"GET", b"k"))
    # MULTI with a queued subscribe: nested confirm, then subscribed
    step("tx", (b"MULTI",))
    step("tx", (b"SUBSCRIBE", b"m1"))
    step("tx", (b"EXEC",))
    step("tx", (b"PING"))
    step("tx", (b"UNSUBSCRIBE", b"m1"))
    step("tx", (b"UNSUBSCRIBE"))               # nothing left: nil frame
    step("sub", (b"PUNSUBSCRIBE", b"p*"))
    step("sub", (b"UNSUBSCRIBE"))
    step("sub", (b"UNSUBSCRIBE"))              # fully bare: nil frame

    # ------------------------------------------------ keyspace notifications
    step("pub", (b"CONFIG", b"SET", b"notify-keyspace-events", b"AKE"))
    step("pub", (b"CONFIG", b"GET", b"notify-keyspace-events"))
    step("sub", (b"PSUBSCRIBE", b"__keyevent@0__:*", b"__keyspace@0__:*"))
    for command in (
        (b"SET", b"k", b"v"),
        (b"SET", b"k", b"v2", b"NX"),
        (b"SET", b"k", b"v3", b"XX"),
        (b"SETNX", b"n1", b"1"),
        (b"SETEX", b"e1", b"100", b"v"),
        (b"GETSET", b"n1", b"2"),
        (b"APPEND", b"k", b"x"),
        (b"SETRANGE", b"k", b"1", b"X"),
        (b"INCR", b"c1"),
        (b"DECRBY", b"c1", b"3"),
        (b"INCRBYFLOAT", b"c1", b"1.5"),
        (b"MSET", b"m1", b"1", b"m2", b"2"),
        (b"DEL", b"m1"),
        (b"GETDEL", b"m2"),
        (b"EXPIRE", b"e1", b"50"),
        (b"EXPIRE", b"e1", b"0"),
        (b"PERSIST", b"k"),
        (b"SET", b"e2", b"v"),
        (b"EXPIREAT", b"e2", b"1"),
        (b"RPUSH", b"l", b"a", b"b"),
        (b"LPUSHX", b"l", b"z"),
        (b"LPOP", b"l"),
        (b"RPOP", b"l", b"1"),
        (b"LREM", b"l", b"0", b"a"),
        (b"LTRIM", b"l", b"0", b"5"),
        (b"LSET", b"l", b"0", b"X"),
        (b"LINSERT", b"l", b"BEFORE", b"X", b"Y"),
        (b"RPUSH", b"l2", b"a", b"b"),
        (b"LMOVE", b"l2", b"l", b"RIGHT", b"LEFT"),
        (b"SADD", b"s", b"a", b"b"),
        (b"SADD", b"s", b"a"),
        (b"SREM", b"s", b"a"),
        (b"SADD", b"s2", b"only"),
        (b"SPOP", b"s2"),
        (b"SADD", b"m", b"x"),
        (b"SADD", b"n", b"y"),
        (b"SMOVE", b"m", b"n", b"x"),
        (b"HSET", b"h", b"f1", b"v"),
        (b"HSET", b"h", b"f1", b"v2"),
        (b"HSETNX", b"h", b"f2", b"w"),
        (b"HINCRBY", b"h", b"n", b"1"),
        (b"HINCRBYFLOAT", b"h", b"nf", b"1.5"),
        (b"HDEL", b"h", b"f2"),
        (b"HEXPIRE", b"h", b"100", b"FIELDS", b"1", b"n"),
        (b"HPERSIST", b"h", b"FIELDS", b"1", b"n"),
        (b"ZADD", b"z", b"1", b"a", b"2", b"b"),
        (b"ZADD", b"z", b"3", b"b"),
        (b"ZINCRBY", b"z", b"1", b"a"),
        (b"ZREM", b"z", b"a"),
        (b"ZADD", b"z2", b"1", b"a"),
        (b"ZPOPMIN", b"z2"),
        (b"SETBIT", b"b1", b"3", b"1"),
        (b"SETBIT", b"b1", b"3", b"1"),
        (b"BITFIELD", b"b1", b"SET", b"u8", b"8", b"7"),
        (b"BITOP", b"OR", b"b2", b"b1"),
    ):
        step("pub", command)
    # class gating: list events off, string events on
    step("pub", (b"CONFIG", b"SET", b"notify-keyspace-events", b"E$"))
    step("pub", (b"SET", b"g1", b"v"))
    step("pub", (b"RPUSH", b"g2", b"a"))
    step("pub", (b"CONFIG", b"SET", b"notify-keyspace-events", b""))

    # ------------------------------------------------------------ WATCH
    step("a", (b"SET", b"wk", b"1"))
    step("a", (b"WATCH", b"wk"))
    step("a", (b"MULTI",))
    step("a", (b"INCR", b"wk"))
    step("a", (b"EXEC",))
    step("a", (b"WATCH", b"wk"))
    step("a", (b"MULTI",))
    step("a", (b"GET", b"wk"))
    step("b", (b"SET", b"wk", b"2"))
    step("a", (b"EXEC",))
    step("a", (b"WATCH", b"wk"))
    step("a", (b"UNWATCH",))
    step("a", (b"MULTI",))
    step("a", (b"INCR", b"wk"))
    step("a", (b"EXEC",))
    step("a", (b"WATCH", b"wk2"))
    step("a", (b"MULTI",))
    step("a", (b"GET", b"wk2"))
    step("b", (b"EXPIRE", b"wk2", b"1"))
    step("a", (b"EXEC",))
    step("a", (b"WATCH", b"wk2"))
    step("a", (b"MULTI",))
    step("a", (b"GET", b"wk2"))
    step("b", (b"SET", b"wk2", b"x"))
    step("b", (b"DEL", b"wk2"))
    step("a", (b"EXEC",))
    step("a", (b"MULTI",))
    step("a", (b"WATCH", b"wk"))
    step("a", (b"DISCARD",))
    step("a", (b"WATCH", b"wk", b"wk"))
    step("a", (b"UNWATCH",))
    step("a", (b"WATCH"))
    # watch on a missing key aborts when another client creates it
    step("a", (b"WATCH", b"brandnew"))
    step("a", (b"MULTI",))
    step("a", (b"GET", b"brandnew"))
    step("b", (b"SET", b"brandnew", b"1"))
    step("a", (b"EXEC",))

    for conn in conns.values():
        conn.drain()
    order = sorted(conns)
    return [(name, conns[name].transcript) for name in order]


def main():
    try:
        probe = socket.create_connection((REDIS_HOST, REDIS_PORT), timeout=2)
        probe.close()
    except OSError:
        print("no redis at %s:%s - start one or set KAGNI_DIFF_REDIS; skipping"
              % (REDIS_HOST, REDIS_PORT))
        return 0
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    kagni_port = free_port()
    kagni = subprocess.Popen(
        [sys.executable, "-m", "kagni", "--port", str(kagni_port), "--db", ":memory:"],
        cwd=repo,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    time.sleep(1.0)
    try:
        real = run(REDIS_HOST, REDIS_PORT)
        ours = run("127.0.0.1", kagni_port)
        mismatches = 0
        for (real_name, real_log), (our_name, our_log) in zip(real, ours):
            if real_log != our_log:
                mismatches += 1
                print("== connection %r differs (%d vs %d frames)"
                      % (real_name, len(real_log), len(our_log)))
                for i, (r, o) in enumerate(zip(real_log, our_log)):
                    if r != o:
                        print("  frame %d:\n    redis: %r\n    kagni: %r" % (i, r, o))
                        break
        print("connections compared: %d, mismatching: %d" % (len(real), mismatches))
        return 1 if mismatches else 0
    finally:
        kagni.terminate()
        try:
            kagni.wait(timeout=5)
        except subprocess.TimeoutExpired:
            kagni.kill()
            kagni.wait(timeout=5)


if __name__ == "__main__":
    sys.exit(main())
