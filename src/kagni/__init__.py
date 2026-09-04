"""Kagni — a Redis-like data store daemon.

Speaks RESP over TCP / unix sockets; snapshots to sqlite.

Run it as a package::

    uv run kagni --help
    uv run python -m kagni --loop trio --port 6380
"""

try:
    from importlib.metadata import version as _version

    __version__ = _version("kagni")
except Exception:  # pragma: no cover - bare checkout without installation
    __version__ = "0.6.2"
