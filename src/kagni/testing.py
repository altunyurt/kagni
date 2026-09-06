"""A pytest fixture that runs a real kagni server for integration tests.

The point of kagni is a genuine Redis-protocol endpoint for tests, so
this exposes one with the least ceremony: a session-scoped fixture that
boots a server on an ephemeral port (in-memory, nothing on disk) and
tears it down afterwards.

Usage - make the plugin available from your tests::

    # tests/conftest.py
    pytest_plugins = ["kagni.testing"]

then request the fixture in any test::

    def test_ping(kagni_server):
        r = redis.Redis(host=kagni_server.host, port=kagni_server.port)
        assert r.ping()

Or point an async client at ``kagni_server.url`` (``redis://host:port``).

The fixture is session-scoped: the store accumulates state across tests
in a session, like a shared test redis.  For a fresh store per test,
boot your own with the public helper and a function-scoped fixture::

    @pytest.fixture
    def fresh_server():
        with kagni.testing.start_server() as server:
            yield server

``start_server`` needs the ``kagni`` package importable from the Python
running the tests (an editable install, or a venv that has it), and it
spawns the server as a subprocess so the test process keeps its own
event loop.
"""

import socket
import subprocess
import sys
import time

try:
    import pytest
except ImportError:  # pytest is optional: only the fixture needs it
    pytest = None

__all__ = ["start_server", "kagni_server"]


class ServerHandle:
    """A running kagni server: ``host``/``port``/``url`` to connect."""

    def __init__(self, process, host, port):
        self._process = process
        self.host = host
        self.port = port

    @property
    def url(self):
        return "redis://%s:%d" % (self.host, self.port)

    def close(self):
        """Terminate the server, waiting briefly before killing it."""
        self._process.terminate()
        try:
            self._process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self._process.kill()
            self._process.wait(timeout=5)

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.close()


def _free_port():
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def start_server():
    """Boot a kagni server on an ephemeral port and wait until it
    accepts connections; use it as a context manager or call
    ``handle.close()`` yourself."""
    port = _free_port()
    process = subprocess.Popen(
        [sys.executable, "-m", "kagni", "--port", str(port), "--db", ":memory:"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    handle = ServerHandle(process, "127.0.0.1", port)
    try:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError("kagni server exited at startup")
            try:
                probe = socket.create_connection((handle.host, handle.port), timeout=0.2)
                probe.close()
                return handle
            except OSError:
                time.sleep(0.05)
        raise RuntimeError("kagni server did not start within 10 seconds")
    except Exception:
        handle.close()
        raise


if pytest is not None:

    @pytest.fixture(scope="session")
    def kagni_server():
        """A session-scoped, in-memory kagni server on an ephemeral port."""
        with start_server() as handle:
            yield handle
