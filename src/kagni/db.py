import logging
import pickle
import threading

log = logging.getLogger(__name__)

try:
    import apsw
except ImportError:  # stdlib fallback keeps the backend usable without apsw
    apsw = None

import sqlite3 as _sqlite3

_SCHEMA = """
create table if not exists data (key blob not null, value blob not null);
"""


def _open(path):
    """Open a backend connection (apsw when available, else stdlib sqlite3).
    Created and used within a single operation so sqlite3's per-thread
    requirement is satisfied when dumps run in a worker thread."""
    if apsw is not None:
        con = apsw.Connection(path)
    else:
        con = _sqlite3.connect(path)
    con.execute("pragma busy_timeout=5000")
    return con


class DB:
    """SQLite snapshot backend.

    ``dump()`` replaces the whole table inside one transaction, so removed
    keys disappear from the store and no duplicate rows can accumulate
    across snapshots (the previous insert-only behaviour resurrected
    deleted keys after a restart).  Short-lived connections are opened per
    operation so the backend can safely be used from worker threads.
    """

    def __init__(self, path):
        self.path = path
        # serializes dump commits against FLUSHDB wipes: the epoch guard
        # in dump() only works if no flush can interleave with a commit
        self._lock = threading.Lock()
        self._prepare()

    def _connect(self):
        return _open(self.path)

    def _prepare(self):
        con = self._connect()
        try:
            con.execute(_SCHEMA)
        finally:
            con.close()

    def dump(self, snapshot, data=None, epoch=None):
        """Persist a full snapshot of *snapshot* (a plain ``{key: value}``
        dict - use ``Data.snapshot()`` for a consistent, off-loop-safe
        copy - or a Data, which is iterated live).

        Blocking sqlite work: run it off the event loop
        (``trio.to_thread.run_sync`` / ``loop.run_in_executor``).

        *data*/*epoch* form an optional freshness guard for snapshots
        taken earlier on the event loop: when the store was flushed
        (FLUSHDB/FLUSHALL clear it, bumping the epoch) after the
        snapshot was taken, the commit stands down - the flush has
        already emptied the table, and committing would resurrect the
        flushed keys.  The check runs under the same lock flush() uses,
        so a flush can never interleave with a commit.
        """
        con = self._connect()
        try:
            with self._lock:
                if data is not None and data.epoch != epoch:
                    # stale snapshot: the flush that emptied the table
                    # already ran (clear() bumps the epoch before the
                    # wipe), so there is nothing to persist
                    return
                with con:  # one transaction per snapshot
                    con.execute(_SCHEMA)
                    con.execute("delete from data")
                    con.executemany(
                        "insert into data values(?,?)",
                        (
                            (key, pickle.dumps(val))
                            for key, val in snapshot.items()
                        ),
                    )
        finally:
            con.close()

    def load(self):
        """Read the persisted snapshot back as a ``{key: value}`` dict."""
        snapshot = {}
        con = self._connect()
        try:
            con.execute(_SCHEMA)
            for key, blob in con.execute("select key, value from data"):
                snapshot[key] = pickle.loads(blob)
        finally:
            con.close()
        return snapshot

    def flush(self):
        """Drop the persisted snapshot (used by FLUSHDB/FLUSHALL)."""
        con = self._connect()
        try:
            with self._lock:
                with con:  # sqlite3 needs an explicit commit for the delete
                    con.execute("delete from data")
        finally:
            con.close()
