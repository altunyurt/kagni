from collections.abc import MutableMapping
from time import monotonic_ns as monotonic_ns_time

__all__ = ["DATA"]


"""
    storage is of type  
    { key: value }

    value is of type 
    {
        value: real value,
        expires_at:  None | timeval 
        _type: some type 
    }

"""


class Data(MutableMapping):
    def __init__(self):
        self._storage = {}

    def __getitem__(self, key):
        val = self._storage.get(key)
        if not val:
            return None

        value = val["value"]
        expires_at = val["expires_at"]
        if not expires_at or expires_at > monotonic_ns_time():
            return value

        # item expired
        del self._storage[key]
        return None

    def __setitem__(self, key, val, expire_secs: int = None):
        # TODO: add type checking for the data
        expires_at = (
            monotonic_ns_time() + expire_secs * (10 ** 9) if expire_secs else None
        )
        self._storage.update({key: {"value": val, "expires_at": expires_at}})

    def __delitem__(self, key):
        if key not in self._storage:
            return 0
        del self._storage[key]
        return 1

    def __contains__(self, key):
        return key in self._storage

    def __iter__(self):
        return iter(self._storage)

    def __len__(self):
        return len(self._storage)

    def get(self, key, default):
        if key not in self._storage:
            return default
        return self.__getitem__(key)

    def expire(self, key, expire_secs):
        if key not in self._storage:
            return 0

        expires_at = (
            monotonic_ns_time() + expire_secs * (10 ** 9) if expire_secs else None
        )
        # TODO: already expired?
        self._storage[key].update({"expires_at": expires_at})
        return 1

    def ttl(self, key: bytes):

        if key not in self._storage:
            return -2

        expires_at = self._storage[key]["expires_at"]

        if not expires_at:
            return -1

        ttl = ceil((expires_at - monotonic_ns_time()) / (10 ** 9))
        return ttl if ttl >= 0 else -2

    def remove(self, key):
        return self.__delitem__(key)


DATA = Data()
