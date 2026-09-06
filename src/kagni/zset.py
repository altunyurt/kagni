"""Sorted-set container for the ZSET commands.

Members are scored with doubles and ordered by ``(score, member)`` like
redis: a dict gives O(1) member lookups, and a plain list kept ordered
with ``bisect`` gives O(log n) search with the list index doubling as
the rank.  Inserts/deletes shift the list with a C-level memmove, which
is the right trade for a Python server (a skip list would pay per-node
Python allocation and interpreted pointer walks until 10^5+ elements
with heavy write churn).

The list is sorted by ``(score, member)`` tuples, so score ties break
on member bytes with zero extra code, and score ranges use key-based
bisect over the score alone (scores are doubles, never NaN).
"""

import bisect
from operator import itemgetter

__all__ = ["ZSet"]

_SCORE = itemgetter(0)


class ZSet:

    def __init__(self, pairs=()):
        self._scores = {}   # member -> score
        self._sorted = []   # [(score, member), ...] ascending
        for member, score in pairs:
            self.add(member, score)

    # ------------------------------------------------------------ queries
    def __len__(self):
        return len(self._sorted)

    def __contains__(self, member):
        return member in self._scores

    def score(self, member):
        """Score of *member*, or None when absent (scores are never None)."""
        return self._scores.get(member)

    def rank(self, member):
        """0-based forward rank of *member*, or None when absent."""
        score = self._scores.get(member)
        if score is None:
            return None
        return bisect.bisect_left(self._sorted, (score, member))

    def pairs(self):
        """Every ``(score, member)`` pair in rank order (a copy)."""
        return list(self._sorted)

    def members(self):
        """Every member in rank order (a copy)."""
        return [member for _, member in self._sorted]

    # ------------------------------------------------------------ writes
    def add(self, member, score):
        """Insert or update *member*; returns True when the score changed.

        A score equal to the current one (``-0.0 == 0.0`` included)
        leaves the entry untouched, like redis' double comparison.
        """
        current = self._scores.get(member)
        if current is not None:
            if current == score:
                return False
            i = bisect.bisect_left(self._sorted, (current, member))
            del self._sorted[i]
        bisect.insort(self._sorted, (score, member))
        self._scores[member] = score
        return True

    def remove(self, member):
        """Delete *member*; returns True when it was present."""
        score = self._scores.pop(member, None)
        if score is None:
            return False
        i = bisect.bisect_left(self._sorted, (score, member))
        del self._sorted[i]
        return True

    # ----------------------------------------------------------- ranges
    def _score_bounds(self, lo, lo_open, hi, hi_open):
        """Index range of entries whose score lies within the window."""
        start = (
            bisect.bisect_right(self._sorted, lo, key=_SCORE)
            if lo_open
            else bisect.bisect_left(self._sorted, lo, key=_SCORE)
        )
        end = (
            bisect.bisect_left(self._sorted, hi, key=_SCORE)
            if hi_open
            else bisect.bisect_right(self._sorted, hi, key=_SCORE)
        )
        return start, end

    def score_pairs(self, lo, lo_open, hi, hi_open):
        """Pairs whose score lies in the window, in rank order."""
        start, end = self._score_bounds(lo, lo_open, hi, hi_open)
        return self._sorted[start:end]

    def member_pairs(self, min_member, min_open, max_member, max_open):
        """Pairs whose member lies in the lexicographic window.

        The walk follows the (score, member) list order and filters on
        the member, like redis' lex commands walk their skiplist (lex
        ordering is only meaningful when all scores are equal, as the
        redis docs say; None bounds mean unbounded).
        """
        out = []
        for score, member in self._sorted:
            if min_member is not None and (
                member < min_member or (min_open and member == min_member)
            ):
                continue
            if max_member is not None and (
                member > max_member or (max_open and member == max_member)
            ):
                continue
            out.append((score, member))
        return out

    # ---------------------------------------------------------- removals
    def remove_rank(self, start, end):
        """Remove the inclusive rank range [start, end], redis-style
        negative-index normalization; returns the number removed."""
        length = len(self._sorted)
        if start < 0:
            start += length
        if end < 0:
            end += length
        if start < 0:
            start = 0
        if start > end or start >= length:
            return 0
        if end >= length:
            end = length - 1
        for score, member in self._sorted[start:end + 1]:
            del self._scores[member]
        del self._sorted[start:end + 1]
        return end - start + 1

    def remove_score(self, lo, lo_open, hi, hi_open):
        """Remove every member whose score lies in the window."""
        start, end = self._score_bounds(lo, lo_open, hi, hi_open)
        if start >= end:
            return 0
        for score, member in self._sorted[start:end]:
            del self._scores[member]
        del self._sorted[start:end]
        return end - start

    def remove_member(self, min_member, min_open, max_member, max_open):
        """Remove every member in the lexicographic window."""
        kept = []
        removed = 0
        for score, member in self._sorted:
            if min_member is not None and (
                member < min_member or (min_open and member == min_member)
            ):
                kept.append((score, member))
                continue
            if max_member is not None and (
                member > max_member or (max_open and member == max_member)
            ):
                kept.append((score, member))
                continue
            del self._scores[member]
            removed += 1
        self._sorted = kept
        return removed

    # ------------------------------------------------------------- misc
    def copy(self):
        new = ZSet()
        new._scores = dict(self._scores)
        new._sorted = list(self._sorted)
        return new
