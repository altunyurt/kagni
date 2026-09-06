"""The kagni.testing pytest fixture: a real server for integration tests."""

import socket


def _pipeline(server, *batches):
    """Send every batch of commands on one connection and return the
    concatenated raw replies (a quiet period ends the read)."""
    s = socket.create_connection((server.host, server.port), timeout=3)
    with s:
        s.settimeout(0.2)
        for args in batches:
            s.sendall(b"*%d\r\n" % len(args) + b"".join(
                b"$%d\r\n%s\r\n" % (len(a), a) for a in args))
        out = b""
        try:
            while True:
                chunk = s.recv(4096)
                if not chunk:
                    break
                out += chunk
        except socket.timeout:
            pass
    return out


def test_kagni_server_fixture(kagni_server):
    assert kagni_server.url.startswith("redis://127.0.0.1:")
    # a real server answers over a real socket: full wire round-trips
    replies = _pipeline(
        kagni_server,
        (b"FLUSHDB",),  # other suites share the session store
        (b"PING",),
        (b"SET", b"k", b"v"),
        (b"GET", b"k"),
        (b"DBSIZE",),
    )
    assert replies == b"+OK\r\n+PONG\r\n+OK\r\n$1\r\nv\r\n:1\r\n", replies
    count = int(_pipeline(kagni_server, (b"COMMAND", b"COUNT")).strip(b":\r\n"))
    assert count > 100


def test_kagni_server_fixture_shared_store(kagni_server):
    # session scope: keys written by the previous test are still there
    assert _pipeline(kagni_server, (b"GET", b"k")) == b"$1\r\nv\r\n"
