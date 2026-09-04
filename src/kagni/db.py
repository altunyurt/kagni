import apsw
import logging
import pickle

log = logging.getLogger(__name__)

_SCHEMA = """
create table if not exists data (key blob not null, value blob not null);
"""


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
        self._prepare()

    def _connect(self):
        con = apsw.Connection(self.path)
        con.execute("pragma busy_timeout=5000")
        return con

    def _prepare(self):
        con = self._connect()
        try:
            con.execute(_SCHEMA)
        finally:
            con.close()

    def dump(self, data):
        """Persist a full snapshot of *data*.

        Blocking sqlite work: run it off the event loop
        (``trio.to_thread.run_sync`` / ``loop.run_in_executor``).
        """
        con = self._connect()
        try:
            with con:  # one transaction per snapshot
                con.execute(_SCHEMA)
                con.execute("delete from data")
                con.executemany(
                    "insert into data values(?,?)",
                    (
                        (key, pickle.dumps(val))
                        for key, val in data.items()
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
            con.execute("delete from data")
        finally:
            con.close()
