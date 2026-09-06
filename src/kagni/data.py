from collections import deque
from collections.abc import MutableMapping
from math import ceil
from time import monotonic_ns as monotonic_ns_time
from time import time_ns as wall_clock_ns

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
        """
        now = monotonic_ns_time()
        out = {}
        dead = []
        for key, entry in self._storage.items():
            if not self._live(entry, now):
                dead.append(key)
                continue
            out[key] = _copy_value(entry["value"])
        for key in dead:
            del self._storage[key]
        return out

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

    def __setitem__(self, key, val, expire_secs: int = None):
        # TODO: add type checking for the data
        expires_at = None
        if expire_secs:
            expires_at = monotonic_ns_time() + expire_secs * (10 ** 9)
        self._storage[key] = {"value": val, "expires_at": expires_at}

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

    def ttl(self, key):
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
        # ceil so that a freshly expired-away key does not report 0 while
        # still logically alive for the remainder of the nanosecond
        return ceil((expires_at - now) / (10 ** 9))

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
    return value
