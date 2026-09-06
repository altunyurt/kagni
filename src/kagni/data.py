from collections import deque
from collections.abc import MutableMapping
from math import ceil
from time import monotonic_ns as monotonic_ns_time
from time import time_ns as wall_clock_ns

from kagni.zset import ZSet

__all__ = ["Data"]

"""
    storage is of type
    { key: value }

    value is of type
    {
        value: real value,
        expires_at:  None | ns-since-boot deadline
    }
"""


class Data(MutableMapping):
    """Key/value store with lazy expiration.

    Expiry model
    ------------
    A key whose ``expires_at`` has passed is *logically missing*: every read
    path (``__getitem__``, ``get``, ``__contains__``) treats it exactly like a
    key that was never stored, which keeps the command layer coherent
    (``GET`` returns NIL, ``DEL`` counts 0, ``KEYS`` does not list it, ...).

    Physical deletion is lazy: single-key accessors purge the key they touch
    and the aggregate views (``__iter__``/``__len__``) sweep the whole table,
    so expired entries cannot linger forever and iteration never mutates a
    dict while walking it.

    API notes (deliberate deviations from the plain-dict contract, kept for
    the command layer): ``__getitem__`` returns ``None`` for a missing or
    expired key instead of raising ``KeyError``, and ``__delitem__`` /
    ``remove`` return ``1``/``0`` (a live value was deleted) instead of
    raising.
    """

    def __init__(self):
        self._storage = {}
        # bumped by clear(): lets an in-flight snapshot commit detect that
        # it predates a FLUSHDB and stand down (see db.DB.dump)
        self.epoch = 0

    # ------------------------------------------------------------------ reads
    def _live(self, entry, now):
        expires_at = entry["expires_at"]
        return expires_at is None or expires_at > now

    def __getitem__(self, key):
        entry = self._storage.get(key)
        if entry is None or not self._live(entry, monotonic_ns_time()):
            return None
        return entry["value"]

    def get(self, key, default=None):
        entry = self._storage.get(key)
        if entry is None:
            return default
        if not self._live(entry, monotonic_ns_time()):
            del self._storage[key]
            return default
        return entry["value"]

    def __contains__(self, key):
        entry = self._storage.get(key)
        return entry is not None and self._live(entry, monotonic_ns_time())

    def _sweep(self):
        """Delete all expired entries.  O(n); used by the aggregate views."""
        now = monotonic_ns_time()
        dead = [
            key
            for key, entry in self._storage.items()
            if not self._live(entry, now)
        ]
        for key in dead:
            del self._storage[key]
        return len(dead)

    def __iter__(self):
        self._sweep()
        return iter(self._storage)

    def __len__(self):
        self._sweep()
        return len(self._storage)

    # ----------------------------------------------------------------- writes
    def clear(self):
        """Drop every key in place (FLUSHDB/FLUSHALL).

        The store is emptied instead of being replaced by a fresh Data so
        long-lived references - the snapshot dumper tasks in the servers
        - keep pointing at the store they empty; the epoch bump makes
        any snapshot taken before the flush fail its commit guard.
        """
        self._storage.clear()
        self.epoch += 1

    def snapshot(self):
        """Consistent copy of every live key, safe to serialize off-loop.

        Call it from the event-loop thread (the single mutator): each
        stored container is duplicated, so later in-place command
        mutations cannot tear the copy while a worker thread pickles it.
        Expired corpses are dropped in the same pass, preserving the
        sweep cadence the periodic dumps used to provide.

        Returns ``{key: (value, wall_deadline_ns)}`` where the deadline
        is None for keys without an expiry: the monotonic expiry is
        converted to an absolute wall-clock deadline here so a snapshot
        survives restarts (the monotonic clock is per-boot).  The
        conversion reads both clocks once; a wall-clock step between an
        expiry being set and the snapshot shifts the stored deadline by
        the step, which is the usual NTP caveat.
        """
        now = monotonic_ns_time()
        now_wall = wall_clock_ns()
        out = {}
        dead = []
        for key, entry in self._storage.items():
            if not self._live(entry, now):
                dead.append(key)
                continue
            expires_at = entry["expires_at"]
            if expires_at is None:
                out[key] = (_copy_value(entry["value"]), None)
            else:
                out[key] = (_copy_value(entry["value"]), now_wall + (expires_at - now))
        for key in dead:
            del self._storage[key]
        return out

    def restore(self, snapshot):
        """Load a persisted snapshot into this (empty) store.

        Accepts ``Data.snapshot()`` output - ``{key: (value,
        wall_deadline_ns)}`` - as well as legacy snapshots holding plain
        values (written before expiries were persisted); legacy keys
        restore without a TTL.  Keys whose wall deadline already passed
        are dropped, like redis discarding expired keys on load.
        """
        now = monotonic_ns_time()
        for key, item in snapshot.items():
            if (
                isinstance(item, tuple)
                and len(item) == 2
                and (item[1] is None or isinstance(item[1], int))
            ):
                value, deadline = item
            else:
                value, deadline = item, None  # legacy snapshot row
            if deadline is None:
                self._storage[key] = {"value": value, "expires_at": None}
                continue
            expires_at = now + (deadline - wall_clock_ns())
            if expires_at <= now:
                continue  # expired while the server was away
            self._storage[key] = {"value": value, "expires_at": expires_at}

    def set(self, key, value, wall_deadline_ns=None, keep_ttl=False):
        """Store a value like redis SET.

        wall_deadline_ns: absolute wall-clock deadline (``time.time_ns()``
        epoch) for EX/PX/EXAT/PXAT style expiries; keep_ttl: preserve the
        existing live TTL instead of clearing it.
        """
        now = monotonic_ns_time()
        entry = self._storage.get(key)
        if keep_ttl and entry is not None and self._live(entry, now):
            expires_at = entry["expires_at"]
        elif wall_deadline_ns is not None:
            expires_at = now + (wall_deadline_ns - wall_clock_ns())
        else:
            expires_at = None
        self._storage[key] = {"value": value, "expires_at": expires_at}

    def __setitem__(self, key, val):
        # plain store: no expiry (commands use set()/expire()/expire_at())
        self._storage[key] = {"value": val, "expires_at": None}

    def __delitem__(self, key):
        """Delete the key (live or expired); return 1 if a live value was
        removed, 0 otherwise.  Missing keys silently return 0."""
        entry = self._storage.pop(key, None)
        if entry is None:
            return 0
        return 1 if self._live(entry, monotonic_ns_time()) else 0

    def remove(self, key):
        return self.__delitem__(key)

    # ------------------------------------------------------------- expiration
    def expire(self, key, expire_secs):
        """Redis EXPIRE semantics.

        - missing or already-expired key -> 0 (expired corpses are purged)
        - non-positive TTL -> the key is deleted and 1 is returned
        - positive TTL -> expiry set, 1 returned
        """
        entry = self._storage.get(key)
        if entry is None:
            return 0
        if not self._live(entry, monotonic_ns_time()):
            del self._storage[key]
            return 0
        if expire_secs <= 0:
            del self._storage[key]
            return 1
        entry["expires_at"] = monotonic_ns_time() + expire_secs * (10 ** 9)
        return 1

    def expire_at(self, key, wall_deadline_ns):
        """Set an absolute wall-clock deadline (EXPIREAT/PEXPIREAT).

        0 for missing or already-expired keys; a past deadline deletes
        the key and returns 1, like a non-positive relative TTL.
        """
        entry = self._storage.get(key)
        if entry is None:
            return 0
        now = monotonic_ns_time()
        if not self._live(entry, now):
            del self._storage[key]
            return 0
        expires_at = now + (wall_deadline_ns - wall_clock_ns())
        if expires_at <= now:
            del self._storage[key]
            return 1
        entry["expires_at"] = expires_at
        return 1

    def ttl(self, key):
        """Redis TTL: whole seconds with redis' rounding - the remaining
        milliseconds are rounded half-up to the nearest second
        (``(ttl_ms + 500) / 1000``)."""
        ms = self.ttl_ms(key)
        if ms < 0:
            return ms
        return (ms + 500) // 1000

    def wall_expiry(self, key):
        """Absolute wall-clock deadline (ns) of a live key's expiry:
        -2 for missing/expired keys, -1 for keys without a TTL.  The
        stored monotonic deadline is converted through the current
        clock offset, so replies can sit up to a millisecond below the
        exact deadline (the wall clock's sampling step); NTP steps
        shift the estimate by the step, like every wall conversion."""
        entry = self._storage.get(key)
        if entry is None:
            return -2
        now = monotonic_ns_time()
        expires_at = entry["expires_at"]
        if expires_at is None:
            return -1
        if expires_at <= now:
            del self._storage[key]
            return -2
        return wall_clock_ns() + (expires_at - now)

    def ttl_ms(self, key):
        """Millisecond TTL (PTTL): redis keeps expiry at ms granularity
        and reports the remaining whole milliseconds."""
        entry = self._storage.get(key)
        if entry is None:
            return -2
        now = monotonic_ns_time()
        expires_at = entry["expires_at"]
        if expires_at is None:
            return -1
        if expires_at <= now:
            del self._storage[key]
            return -2
        # ceil over ns matches redis' floor over its ms clock, so a key
        # set a fraction of a millisecond ago still reports the full ms
        return ceil((expires_at - now) / 1_000_000)

    def keyspace_stats(self):
        """(keys, expiring keys, avg remaining ms) for INFO keyspace."""
        self._sweep()
        now = monotonic_ns_time()
        expires = 0
        ttl_sum = 0
        for entry in self._storage.values():
            expires_at = entry["expires_at"]
            if expires_at is not None:
                expires += 1
                ttl_sum += expires_at - now
        avg = ttl_sum // expires // 1_000_000 if expires else 0
        return len(self._storage), expires, avg

    def persist(self, key):
        """Remove the TTL of a live key (1), or 0 for missing/expired keys."""
        entry = self._storage.get(key)
        if entry is None:
            return 0
        if not self._live(entry, monotonic_ns_time()):
            del self._storage[key]
            return 0
        entry["expires_at"] = None
        return 1


def _copy_value(value):
    """Duplicate a stored value so later in-place command mutations cannot
    affect a snapshot taken from the loop thread."""
    if isinstance(value, bytes):
        return value
    if isinstance(value, dict):  # hash
        return dict(value)
    if isinstance(value, set):  # set
        return set(value)
    if isinstance(value, deque):  # list
        return deque(value)
    if type(value).__name__ == "BitMap":  # pyroaring, imported lazily
        return value.copy()
    if isinstance(value, ZSet):
        return value.copy()
    return value
