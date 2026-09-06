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

from kagni.constants import Error, Errors, Response
from .common import KIND_LIST, expect_kind, string2ll
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
        # keep_ttl: redis LTRIM trims in place and leaves the TTL alone
        self.data.set(key, deque(islice(lst, start, end + 1)), keep_ttl=True)
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
                # keep_ttl: redis LREM trims in place and leaves the TTL alone
                self.data.set(key, kept, keep_ttl=True)
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

    # ------------------------------------------------------------- moves
    def _list_side(self, where):
        """True for LEFT, False for RIGHT; redis parses these before any
        key lookup, so a bad value is a syntax error even for missing keys."""
        side = where.upper()
        if side == b"LEFT":
            return True
        if side == b"RIGHT":
            return False
        raise Errors.SYNTAX

    def _move(self, source, destination, from_left, to_left):
        src = self._list(source)
        if src is None:
            return Response.NIL
        if not src:  # defensive: stored lists are never empty
            self.data.remove(source)
            return Response.NIL

        # destination is type-checked before anything is popped; when the
        # source and destination are the same key the element is rotated
        # inside the list
        dst = src if destination == source else self._list(destination)

        value = src.popleft() if from_left else src.pop()
        if dst is None:
            dst = deque()
            self.data[destination] = dst
        if to_left:
            dst.appendleft(value)
        else:
            dst.append(value)

        if dst is not src and not src:
            self.data.remove(source)
        return value

    @command_decorator(b"LMOVE")
    def LMOVE(
        self,
        source: bytes,
        destination: bytes,
        wherefrom: bytes,
        whereto: bytes,
    ) -> (bytes, Response.NIL):
        from_left = self._list_side(wherefrom)
        to_left = self._list_side(whereto)
        return self._move(source, destination, from_left, to_left)

    @command_decorator(b"RPOPLPUSH")
    def RPOPLPUSH(self, source: bytes, destination: bytes) -> (bytes, Response.NIL):
        return self._move(source, destination, from_left=False, to_left=True)

    @command_decorator(b"LMPOP")
    def LMPOP(self, numkeys: int, *rest: bytes):
        """LMPOP numkeys key [key ...] LEFT|RIGHT [COUNT count]

        Pops from the first non-empty list among the keys, checking them
        in the order given; replies [key, [elements...]] or a null array.
        Arg parsing mirrors redis' lmpopGenericCommand: the LEFT|RIGHT
        position is derived from the declared numkeys, so key-count
        mismatches and stray options are syntax errors; numkeys/count
        must be >= 1 with redis' exact error messages.
        """
        if numkeys < 1:
            raise Error("ERR", "numkeys should be greater than 0")
        if numkeys + 1 > len(rest):
            raise Errors.SYNTAX

        keys = rest[:numkeys]
        from_left = self._list_side(rest[numkeys])

        count = 1
        j = numkeys + 1
        while j < len(rest):
            option = rest[j].upper()
            if option == b"COUNT" and j + 1 < len(rest):
                try:
                    count = string2ll(rest[j + 1])
                except ValueError:
                    raise Errors.NOT_INT
                if count < 1:
                    raise Error("ERR", "count should be greater than 0")
                j += 2
                if j < len(rest):
                    raise Errors.SYNTAX  # COUNT may only appear once
            else:
                raise Errors.SYNTAX

        for key in keys:
            lst = self._list(key)
            if lst is None:
                continue
            if not lst:  # defensive: stored lists are never empty
                self.data.remove(key)
                continue

            popfn = lst.popleft if from_left else lst.pop
            n = min(count, len(lst))
            popped = [popfn() for _ in range(n)]
            self._drop_empty(key, lst)
            return [key, popped]

        return Response.NIL_ARRAY

    # --------------------------------------------------------------- lpos
    @command_decorator(b"LPOS")
    def LPOS(self, key: bytes, element: bytes, *options: bytes):
        rank = 1
        count = -1  # -1: COUNT option not given
        maxlen = 0  # 0: scan the whole list

        # parse options before any key lookup, like redis (RANK/COUNT/MAXLEN)
        j = 0
        while j < len(options):
            option = options[j].upper()
            if option not in (b"RANK", b"COUNT", b"MAXLEN") or j + 1 >= len(options):
                raise Errors.SYNTAX
            try:
                value = string2ll(options[j + 1])
            except ValueError:
                raise Errors.NOT_INT
            j += 2

            if option == b"RANK":
                if value == 0:
                    raise Errors.RANK_ZERO
                rank = value
            elif option == b"COUNT":
                if value < 0:
                    raise Errors.COUNT_NEG
                count = value
            else:  # MAXLEN
                if value < 0:
                    raise Errors.MAXLEN_NEG
                maxlen = value

        lst = self._list(key)
        if lst is None:
            return Response.NIL if count == -1 else []

        length = len(lst)
        from_tail = rank < 0
        if from_tail:
            rank = -rank

        matches = 0
        found = []
        for index, item in enumerate(lst if not from_tail else reversed(lst)):
            if maxlen and index >= maxlen:
                break
            if item != element:
                continue
            matches += 1
            if matches < rank:
                continue
            match_index = length - 1 - index if from_tail else index
            if count == -1:
                return match_index
            found.append(match_index)
            if count and len(found) >= count:
                break

        return Response.NIL if count == -1 else found
