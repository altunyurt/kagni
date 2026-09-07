"""A peer that resets the connection (no FIN farewell) must be handled
quietly: redis-benchmark and other clients kill connections with RST,
and the trio backend used to log a nursery ExceptionGroup as
"connection handler failed" for that routine event."""

import os
import signal
import socket
import struct
import subprocess
import sys
import time

from kagni.resp import RESPReader


def _rst_close(sock):
    """Close with RST (SO_LINGER 0), the way impatient clients do."""
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))
    sock.close()


def test_trio_connection_reset_is_quiet(tmp_path):
    port = 6398
    logfile = tmp_path / "kagni.log"
    server = subprocess.Popen(
        [sys.executable, "-m", "kagni", "--loop", "trio",
         "--port", str(port), "--db", ":memory:"],
        stdout=subprocess.DEVNULL,
        stderr=open(logfile, "ab"),
    )
    try:
        for _ in range(40):
            try:
                probe = socket.create_connection(("127.0.0.1", port), timeout=0.3)
                probe.close()
                break
            except OSError:
                time.sleep(0.25)
        else:
            raise AssertionError("trio server did not start")

        def conn():
            s = socket.create_connection(("127.0.0.1", port), timeout=2)
            s.settimeout(0.5)
            return s, RESPReader(engine="python")

        # a subscriber connection that gets RSTed while a push is
        # heading its way exercises both the reader and writer paths
        sub, reader = conn()
        sub.sendall(b"*2\r\n$9\r\nSUBSCRIBE\r\n$4\r\nchan\r\n")
        got = []
        try:
            while True:
                chunk = sub.recv(65536)
                if not chunk:
                    break
                got.extend(m for m in reader.feed(chunk) if m is not None)
        except socket.timeout:
            pass
        assert got == [[b"subscribe", b"chan", 1]]

        pub, pub_reader = conn()
        pub.sendall(b"*3\r\n$7\r\nPUBLISH\r\n$4\r\nchan\r\n$1\r\nx\r\n")
        time.sleep(0.1)
        _rst_close(sub)  # reset mid-connection

        # the server stays alive and answers on new connections
        time.sleep(0.3)
        check, check_reader = conn()
        check.sendall(b"*1\r\n$4\r\nPING\r\n")
        assert check_reader.feed(check.recv(65536))[0] == b"+PONG"
        check.close()
        pub.close()
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait(timeout=5)

    time.sleep(0.2)
    log = logfile.read_bytes()
    assert b"connection handler failed" not in log, log[-2000:]
    assert b"Traceback" not in log, log[-2000:]
