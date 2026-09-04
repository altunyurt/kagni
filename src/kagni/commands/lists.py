"""Redis list commands, backed by a ``collections.deque`` of bytes.

Semantics mirror redis' t_list.c (verified against 7.2):

- a deque gives O(1) pushes/pops at both ends like redis' quicklist
- empty lists are deleted immediately (the redis invariant), so a stored
  list is never empty; commands defensively treat one as missing anyway
- LRANGE/LTRIM index handling: negatives are relative to the tail and
  only the start index is clamped to 0; the range is empty when
  ``start > end`` or ``start >= length`` (this also covers an end index
  that is still negative after normalisation)
- LSET errors: ``ERR no such key`` on a missing key, ``ERR index out of
  range`` when the index is out of range; LINDEX returns NIL instead
- LPOP/RPOP with count reply with a *null* array (``*-1``) on a missing
  key but an *empty* array for count 0; popped ranges are returned in
  pop order (RPOP count returns tail-first)
- LINSERT validates BEFORE|AFTER before looking the key up
"""

from collections import deque
from itertools import islice
from typing import List

from kagni.constants import Errors, Response
from .common import KIND_LIST, expect_kind
from .decorator import command_decorator

__all__ = ["CommandSetMixin"]


class CommandSetMixin:

    # ------------------------------------------------------------- helpers
    def _list(self, key):
        """deque stored under *key*; None when missing/expired."""
        return expect_kind(self.data, key, KIND_LIST)

    def _drop_empty(self, key, lst):
        if not lst:
            self.data.remove(key)

    def _require_value(self, vals, command):
        if not vals:
            raise Errors.arity(command)

    def _push(self, key, vals, left, xx):
        lst = self._list(key)
        if lst is None:
            if xx:
                return 0
            lst = deque()
            self.data[key] = lst
        if left:
            lst.extendleft(vals)  # last argument ends up at the head
        else:
            lst.extend(vals)
        return len(lst)

    # -------------------------------------------------------------- pushes
    @command_decorator(b"LPUSH")
    def LPUSH(self, key: bytes, *vals: List[bytes]) -> int:
        self._require_value(vals, "lpush")
        return self._push(key, vals, left=True, xx=False)

    @command_decorator(b"RPUSH")
    def RPUSH(self, key: bytes, *vals: List[bytes]) -> int:
        self._require_value(vals, "rpush")
        return self._push(key, vals, left=False, xx=False)

    @command_decorator(b"LPUSHX")
    def LPUSHX(self, key: bytes, *vals: List[bytes]) -> int:
        self._require_value(vals, "lpushx")
        return self._push(key, vals, left=True, xx=True)

    @command_decorator(b"RPUSHX")
    def RPUSHX(self, key: bytes, *vals: List[bytes]) -> int:
        self._require_value(vals, "rpushx")
        return self._push(key, vals, left=False, xx=True)

    # -------------------------------------------------------------- reads
    @command_decorator(b"LLEN")
    def LLEN(self, key: bytes) -> int:
        lst = self._list(key)
        return 0 if lst is None else len(lst)

    @command_decorator(b"LRANGE")
    def LRANGE(self, key: bytes, start: int, end: int) -> List[bytes]:
        lst = self._list(key)
        if lst is None:
            return []

        length = len(lst)
        if start < 0:
            start += length
        if end < 0:
            end += length
        if start < 0:
            start = 0
        # invariant: start >= 0, so this also covers an end still < 0
        if start > end or start >= length:
            return []
        if end >= length:
            end = length - 1
        return list(islice(lst, start, end + 1))

    @command_decorator(b"LINDEX")
    def LINDEX(self, key: bytes, index: int) -> (bytes, Response.NIL):
        lst = self._list(key)
        if lst is None:
            return Response.NIL
        length = len(lst)
        i = index if index >= 0 else length + index
        if i < 0 or i >= length:
            return Response.NIL
        return lst[i]

    # -------------------------------------------------------------- pops
    def _pop(self, key, count, left):
        if count is not None and count < 0:
            raise Errors.NOT_POSITIVE

        lst = self._list(key)
        if lst is None:
            # redis: missing key + count -> null array, not an empty one
            return Response.NIL if count is None else Response.NIL_ARRAY
        if count == 0:
            return []
        if not lst:  # defensive: stored lists are never empty
            self.data.remove(key)
            return Response.NIL if count is None else Response.NIL_ARRAY

        popfn = lst.popleft if left else lst.pop
        if count is None:
            val = popfn()
            self._drop_empty(key, lst)
            return val

        n = min(count, len(lst))
        popped = [popfn() for _ in range(n)]
        self._drop_empty(key, lst)
        return popped

    @command_decorator(b"LPOP")
    def LPOP(self, key: bytes, count: int = None) -> (bytes, List[bytes]):
        return self._pop(key, count, left=True)

    @command_decorator(b"RPOP")
    def RPOP(self, key: bytes, count: int = None) -> (bytes, List[bytes]):
        return self._pop(key, count, left=False)

    # ---------------------------------------------------------- mutations
    @command_decorator(b"LSET")
    def LSET(self, key: bytes, index: int, val: bytes) -> Response.OK:
        lst = self._list(key)
        if lst is None:
            raise Errors.NOKEY
        length = len(lst)
        i = index if index >= 0 else length + index
        if i < 0 or i >= length:
            raise Errors.INDEX_RANGE
        lst[i] = val
        return Response.OK

    @command_decorator(b"LTRIM")
    def LTRIM(self, key: bytes, start: int, end: int) -> Response.OK:
        lst = self._list(key)
        if lst is None:
            return Response.OK

        length = len(lst)
        if start < 0:
            start += length
        if end < 0:
            end += length
        if start < 0:
            start = 0
        if start > end or start >= length:
            # whole list out of range: trim to nothing
            self.data.remove(key)
            return Response.OK
        if end >= length:
            end = length - 1
        if start == 0 and end == length - 1:
            return Response.OK  # trim to the full list is a no-op
        self.data[key] = deque(islice(lst, start, end + 1))
        return Response.OK

    @command_decorator(b"LREM")
    def LREM(self, key: bytes, count: int, val: bytes) -> int:
        lst = self._list(key)
        if lst is None:
            return 0

        removed = 0
        kept = deque()
        if count >= 0:
            # count == 0 removes every match; positive counts stop early
            for item in lst:
                if item == val and (count == 0 or removed < count):
                    removed += 1
                else:
                    kept.append(item)
        else:
            # negative count: remove up to |count| matches from the tail
            limit = -count
            for item in reversed(lst):
                if item == val and removed < limit:
                    removed += 1
                else:
                    kept.appendleft(item)

        if removed:
            if kept:
                self.data[key] = kept
            else:
                self.data.remove(key)
        return removed

    @command_decorator(b"LINSERT")
    def LINSERT(self, key: bytes, where: bytes, pivot: bytes, val: bytes) -> int:
        # redis validates BEFORE|AFTER before looking the key up
        if where.upper() == b"BEFORE":
            offset = 0
        elif where.upper() == b"AFTER":
            offset = 1
        else:
            raise Errors.SYNTAX

        lst = self._list(key)
        if lst is None:
            return 0
        for i, item in enumerate(lst):
            if item == pivot:
                lst.insert(i + offset, val)
                return len(lst)
        return -1
