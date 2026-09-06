"""CLI parsing and unix-socket helper tests for the kagni.py launcher."""

import os
import socket
import tempfile

from kagni import cli


def test_cli_defaults():
    config = cli._parse([])
    assert config.loop == "asyncio"
    assert config.host == "localhost"
    assert config.port == 6379
    assert config.socket_path is None
    assert config.dump_interval == 20
    assert config.no_uvloop is False
    assert config.db_path
    assert config.save is True
    assert config.daemon is False
    assert config.pidfile is None
    assert config.logfile is None


def test_cli_validation_errors():
    # --port 0 without a socket leaves nothing to listen on
    for argv in (["--port", "0"], ["--port", "70000"], ["--port", "-1"]):
        try:
            cli._parse(argv)
        except SystemExit:
            continue
        raise AssertionError("expected SystemExit for %r" % (argv,))

    try:
        cli._parse(["--loop", "gevent"])
    except SystemExit:
        pass
    else:
        raise AssertionError("expected SystemExit for an unknown loop")

    try:
        cli._parse(["--dump-interval", "0"])
    except SystemExit:
        pass
    else:
        raise AssertionError("expected SystemExit for a zero dump interval")


def test_cli_tcp_and_socket_are_additive():
    # like redis: --socket adds a unix listener, --port 0 turns TCP off
    config = cli._parse(["--port", "7000", "--socket", "/tmp/kagni.sock"])
    assert config.port == 7000
    assert config.socket_path == "/tmp/kagni.sock"
    assert config.host == "localhost"

    config = cli._parse(["--port", "0", "--socket", "/tmp/kagni.sock"])
    assert config.port == 0
    assert config.socket_path == "/tmp/kagni.sock"


def test_cli_full_flags():
    config = cli._parse(
        [
            "--loop", "trio",
            "--host", "127.0.0.1",
            "--port", "7777",
            "--socket", "/tmp/kagni.sock",
            "--db", "/tmp/kagni.sqlite",
            "--dump-interval", "5",
            "--no-uvloop",
        ]
    )
    assert config.loop == "trio"
    assert config.host == "127.0.0.1"
    assert config.port == 7777
    assert config.socket_path == "/tmp/kagni.sock"
    assert config.db_path == "/tmp/kagni.sqlite"
    assert config.dump_interval == 5
    assert config.no_uvloop is True


def test_cli_memory_db():
    config = cli._parse(["--db", ":memory:"])
    assert config.db_path == ":memory:"


def test_cli_no_save_flag():
    assert cli._parse([]).save is True
    config = cli._parse(["--no-save"])
    assert config.save is False
    # orthogonal to the store choice: :memory: + --no-save is fine
    config = cli._parse(["--db", ":memory:", "--no-save"])
    assert config.db_path == ":memory:" and config.save is False


def test_cli_daemon_flags():
    config = cli._parse(
        ["--daemon", "--pidfile", "/tmp/kagni.pid", "--logfile", "/tmp/kagni.log"]
    )
    assert config.daemon is True
    assert config.pidfile == "/tmp/kagni.pid"
    assert config.logfile == "/tmp/kagni.log"


def test_prepare_socket_path_removes_stale_file():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "kagni.sock")
        with open(path, "w") as fh:
            fh.write("leftover from a crashed run")
        assert cli.prepare_socket_path(path) == path
        assert not os.path.exists(path)


def test_prepare_socket_path_refuses_live_server():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "kagni.sock")
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(path)
        server.listen(1)
        try:
            try:
                cli.prepare_socket_path(path)
            except RuntimeError:
                pass
            else:
                raise AssertionError("expected RuntimeError for a live socket")
            assert os.path.exists(path)  # live server's file must survive
        finally:
            server.close()
            os.unlink(path)


def test_remove_socket_file():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "kagni.sock")
        assert cli.remove_socket_file(path) is None  # missing file is fine
        with open(path, "w") as fh:
            fh.write("x")
        cli.remove_socket_file(path)
        assert not os.path.exists(path)
