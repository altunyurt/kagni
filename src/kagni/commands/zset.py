"""Redis sorted-set commands (targets redis 7.4 semantics).

Values are :class:`kagni.zset.ZSet` containers: a member->score dict
plus a (score, member) list kept ordered with bisect, so the list index
is the rank and score ranges bisect on the score alone.

The unified ZRANGE (6.2+) and the classic per-direction commands share
one range engine; ZRANGEBYSCORE/ZREVRANGEBYSCORE/ZRANGEBYLEX/
ZREVRANGEBYLEX/ZREVRANGE are thin wrappers over it, like redis'
aliases.  Range bounds are validated before any key lookup (redis
order), so a bad bound errors even on a missing key.  Redis lex
commands only promise member ordering when all scores are equal (their
docs say so); like redis' skiplist walk, the lex window filters the
(score, member)-ordered list.
"""

from random import choice, sample

from kagni.constants import Error, Errors, Response
from kagni.zset import ZSet
from .common import (
    KIND_ZSET,
    _format_float,
    _parse_float,
    expect_kind,
    string2ll,
)
from .decorator import command_decorator

__all__ = ["CommandSetMixin"]


class CommandSetMixin:

    def _zset(self, key):
        """ZSet stored under *key*; None when missing/expired."""
        return expect_kind(self.data, key, KIND_ZSET)

    def _drop_empty(self, key, zset):
        if not len(zset):
            # redis: the key disappears with its last member
            self.data.remove(key)

    # ------------------------------------------------------------ helpers
    @staticmethod
    def _score_bound(raw):
        """One BYSCORE bound: an optional '(' prefix marks the bound as
        exclusive; otherwise redis' "min or max is not a float"."""
        exclusive = raw[:1] == b"("
        if exclusive:
            raw = raw[1:]
        try:
            value = _parse_float(raw)
        except Error:
            raise Errors.MIN_MAX_FLOAT
        return value, exclusive

    @staticmethod
    def _lex_bound(raw, is_min):
        """One BYLEX bound: '-'/'+' are unbounded ends usable on either
        side ('-' as max or '+' as min just yield an empty window), and
        '[' / '(' prefix a member (the prefix alone means the empty
        member).  Returns (member, exclusive, degenerate); degenerate
        windows match nothing."""
        if raw == b"-":
            return (None, False, not is_min)
        if raw == b"+":
            return (None, False, is_min)
        prefix = raw[:1]
        if prefix in (b"[", b"("):
            return raw[1:], prefix == b"(", False
        raise Errors.LEX_RANGE

    @staticmethod
    def _interleave(pairs, withscores):
        """Reply list for a (score, member) pair list: members, or
        member/score alternating when WITHSCORES."""
        if not withscores:
            return [member for _, member in pairs]
        out = []
        for score, member in pairs:
            out.append(member)
            out.append(_format_float(score).encode())
        return out

    @staticmethod
    def _slice_ranks(pairs, start, end):
        """Rank-window slice with redis' negative-index handling (the
        LRANGE conventions)."""
        length = len(pairs)
        if start < 0:
            start += length
        if end < 0:
            end += length
        if start < 0:
            start = 0
        if start > end or start >= length:
            return []
        if end >= length:
            end = length - 1
        return pairs[start:end + 1]

    # ---------------------------------------------------------------- zadd
    def _parse_zadd_flags(self, args):
        nx = xx = gt = lt = ch = incr = False
        j = 0
        while j < len(args):
            opt = args[j].upper()
            if opt == b"NX":
                nx = True
            elif opt == b"XX":
                xx = True
            elif opt == b"GT":
                gt = True
            elif opt == b"LT":
                lt = True
            elif opt == b"CH":
                ch = True
            elif opt == b"INCR":
                incr = True
            else:
                break  # the first non-option token starts score/member pairs
            j += 1
        if nx and xx:
            raise Errors.ZADD_XX_NX
        if (gt and lt) or (nx and (gt or lt)):
            raise Errors.ZADD_CONFLICT
        return nx, xx, gt, lt, ch, incr, j

    @command_decorator(b"ZADD")
    def ZADD(self, key: bytes, *args: bytes):
        """ZADD key [NX|XX] [GT|LT] [CH] [INCR] score member [score member ...]"""
        nx, xx, gt, lt, ch, incr, j = self._parse_zadd_flags(args)
        if len(args) < 2:  # at least one score/member pair after the key
            raise Errors.arity("zadd")
        rest = args[j:]
        if len(rest) % 2:
            raise Errors.SYNTAX
        if incr and len(rest) != 2:
            raise Errors.ZADD_INCR_PAIR

        zset = self._zset(key)
        if zset is None and xx:
            # XX never creates: nothing to update on a missing key
            return Response.NIL if incr else 0

        added = 0
        changed = 0
        for i in range(0, len(rest), 2):
            score = _parse_float(rest[i])
            member = rest[i + 1]
            current = zset.score(member) if zset is not None else None

            if incr:
                existed = current is not None
                if current is None:
                    if xx:
                        return Response.NIL
                    current = 0.0
                elif nx:
                    return Response.NIL  # NX never touches an existing member
                score = current + score
                if score != score:  # NaN result (e.g. inf + -inf)
                    raise Errors.NAN_RESULT
                # GT/LT gate updates only: a brand-new member is added
                # whatever the comparison against an implicit 0 would say
                if existed and (
                    (gt and score <= current) or (lt and score >= current)
                ):
                    return Response.NIL
                if zset is None:
                    zset = self._create_zset(key)
                zset.add(member, score)
                return _format_float(score).encode()

            if current is None:
                if xx:  # XX only updates existing members
                    continue
                if zset is None:
                    zset = self._create_zset(key)
                zset.add(member, score)
                added += 1
            else:
                if nx or (gt and score <= current) or (lt and score >= current):
                    continue
                if zset.add(member, score):
                    changed += 1
        return added + changed if ch else added

    def _create_zset(self, key):
        zset = ZSet()
        self.data[key] = zset
        return zset

    @command_decorator(b"ZINCRBY")
    def ZINCRBY(self, key: bytes, increment: bytes, member: bytes) -> bytes:
        increment = _parse_float(increment)
        zset = self._zset(key)
        current = zset.score(member) if zset is not None else None
        new_score = (0.0 if current is None else current) + increment
        if new_score != new_score:  # NaN result (e.g. inf + -inf)
            raise Errors.NAN_RESULT
        if zset is None:
            zset = self._create_zset(key)
        zset.add(member, new_score)
        return _format_float(new_score).encode()

    # ------------------------------------------------------------- basics
    @command_decorator(b"ZCARD")
    def ZCARD(self, key: bytes) -> int:
        zset = self._zset(key)
        return 0 if zset is None else len(zset)

    @command_decorator(b"ZSCORE")
    def ZSCORE(self, key: bytes, member: bytes) -> (bytes, Response.NIL):
        zset = self._zset(key)
        if zset is None:
            return Response.NIL
        score = zset.score(member)
        return Response.NIL if score is None else _format_float(score).encode()

    @command_decorator(b"ZMSCORE")
    def ZMSCORE(self, key: bytes, *members: bytes) -> list:
        if not members:
            raise Errors.arity("zmscore")
        zset = self._zset(key)
        out = []
        for member in members:
            score = zset.score(member) if zset is not None else None
            out.append(Response.NIL if score is None else _format_float(score).encode())
        return out

    @command_decorator(b"ZRANK")
    def ZRANK(self, key: bytes, member: bytes, *options: bytes):
        return self._zrank(key, member, options, reverse=False)

    @command_decorator(b"ZREVRANK")
    def ZREVRANK(self, key: bytes, member: bytes, *options: bytes):
        return self._zrank(key, member, options, reverse=True)

    def _zrank(self, key, member, options, reverse):
        withscore = False
        for option in options:
            if option.upper() == b"WITHSCORE":
                withscore = True
            else:
                raise Errors.SYNTAX
        zset = self._zset(key)
        rank = zset.rank(member) if zset is not None else None
        if rank is None:
            # redis replies a null array with WITHSCORE, a null bulk
            # without it
            return Response.NIL_ARRAY if withscore else Response.NIL
        if reverse:
            rank = len(zset) - 1 - rank
        if not withscore:
            return rank
        return [rank, _format_float(zset.score(member)).encode()]

    # ------------------------------------------------------------- ranges
    def _parse_range_options(self, options):
        """Shared option scan for the range commands.  Returns
        (mode, rev, withscores, limit), mode being None for the plain
        rank grammar; raises redis' syntax errors (duplicate REV and
        unsupported combinations included, duplicate WITHSCORES
        tolerated)."""
        mode = None
        rev = False
        withscores = False
        limit = None
        j = 0
        while j < len(options):
            opt = options[j].upper()
            if opt in (b"BYSCORE", b"BYLEX"):
                if mode is not None:
                    raise Errors.SYNTAX
                mode = b"byscore" if opt == b"BYSCORE" else b"bylex"
                j += 1
            elif opt == b"REV":
                if rev:
                    raise Errors.SYNTAX
                rev = True
                j += 1
            elif opt == b"WITHSCORES":
                withscores = True
                j += 1
            elif opt == b"LIMIT" and j + 2 < len(options):
                if limit is not None:
                    raise Errors.SYNTAX
                try:
                    limit = (string2ll(options[j + 1]), string2ll(options[j + 2]))
                except ValueError:
                    raise Errors.NOT_INT
                j += 3
            else:
                raise Errors.SYNTAX
        if withscores and mode == b"bylex":
            raise Errors.WITHSCORES_BYLEX
        if limit is not None and mode is None:
            raise Errors.LIMIT_NEEDS_BY
        return mode, rev, withscores, limit

    @staticmethod
    def _parse_bounds(start_raw, stop_raw, mode, rev):
        """Validate and parse the start/stop tokens for the mode; with
        REV the bounds are given in reverse order (max first).  Raises
        before any key lookup, like redis."""
        lo_raw, hi_raw = (start_raw, stop_raw) if not rev else (stop_raw, start_raw)
        if mode is None:
            try:
                start = string2ll(start_raw)
                stop = string2ll(stop_raw)
            except ValueError:
                raise Errors.NOT_INT
            return (start, stop), False
        if mode == b"byscore":
            lo, lo_open = CommandSetMixin._score_bound(lo_raw)
            hi, hi_open = CommandSetMixin._score_bound(hi_raw)
            return (lo, lo_open, hi, hi_open), False
        lo, lo_open, lo_dead = CommandSetMixin._lex_bound(lo_raw, is_min=True)
        hi, hi_open, hi_dead = CommandSetMixin._lex_bound(hi_raw, is_min=False)
        return (lo, lo_open, hi, hi_open), lo_dead or hi_dead

    def _range_pairs(self, zset, parsed, mode, rev):
        """The (score, member) pairs a range selects, in reply order."""
        if mode is None:
            start, stop = parsed
            pairs = zset.pairs()
            if rev:
                pairs.reverse()
            return self._slice_ranks(pairs, start, stop)
        lo, lo_open, hi, hi_open = parsed
        if mode == b"byscore":
            pairs = zset.score_pairs(lo, lo_open, hi, hi_open)
        else:
            pairs = zset.member_pairs(lo, lo_open, hi, hi_open)
        if rev:
            pairs.reverse()
        return pairs

    def _limit_pairs(self, pairs, limit):
        if limit is None:
            return pairs
        offset, count = limit
        if offset < 0:
            # redis treats a negative offset as an empty result (the skip
            # consumes an already-finished walk)
            return []
        if count < 0:
            count = len(pairs)  # a negative count means: no limit
        return pairs[offset:offset + count]

    @command_decorator(b"ZRANGE")
    def ZRANGE(self, key: bytes, start: bytes, stop: bytes, *options: bytes):
        """ZRANGE key start stop [BYSCORE|BYLEX] [REV] [LIMIT offset count]
        [WITHSCORES] (the unified redis 6.2+ grammar)."""
        mode, rev, withscores, limit = self._parse_range_options(options)
        parsed, empty = self._parse_bounds(start, stop, mode, rev)
        zset = self._zset(key)
        if zset is None or empty:
            return []
        pairs = self._range_pairs(zset, parsed, mode, rev)
        return self._interleave(self._limit_pairs(pairs, limit), withscores)

    @command_decorator(b"ZREVRANGE")
    def ZREVRANGE(self, key: bytes, start: bytes, stop: bytes, *options: bytes):
        withscores = False
        for option in options:
            if option.upper() == b"WITHSCORES":
                withscores = True
            else:
                raise Errors.SYNTAX
        parsed, empty = self._parse_bounds(start, stop, None, rev=True)
        zset = self._zset(key)
        if zset is None or empty:
            return []
        pairs = self._range_pairs(zset, parsed, None, rev=True)
        return self._interleave(pairs, withscores)

    def _legacy_score_range(self, key, first, second, options, reverse):
        """Shared ZRANGEBYSCORE/ZREVRANGEBYSCORE engine; the reverse
        command takes its bounds as (max, min)."""
        withscores = False
        limit = None
        j = 0
        while j < len(options):
            opt = options[j].upper()
            if opt == b"WITHSCORES":
                withscores = True
                j += 1
            elif opt == b"LIMIT" and j + 2 < len(options):
                if limit is not None:
                    raise Errors.SYNTAX
                try:
                    limit = (string2ll(options[j + 1]), string2ll(options[j + 2]))
                except ValueError:
                    raise Errors.NOT_INT
                j += 3
            else:
                raise Errors.SYNTAX
        parsed, empty = self._parse_bounds(first, second, b"byscore", False)
        zset = self._zset(key)
        if zset is None or empty:
            return []
        pairs = self._range_pairs(zset, parsed, b"byscore", reverse)
        return self._interleave(self._limit_pairs(pairs, limit), withscores)

    @command_decorator(b"ZRANGEBYSCORE")
    def ZRANGEBYSCORE(self, key: bytes, min_: bytes, max_: bytes, *options: bytes):
        return self._legacy_score_range(key, min_, max_, options, reverse=False)

    @command_decorator(b"ZREVRANGEBYSCORE")
    def ZREVRANGEBYSCORE(self, key: bytes, max_: bytes, min_: bytes, *options: bytes):
        return self._legacy_score_range(key, min_, max_, options, reverse=True)

    def _legacy_lex_range(self, key, first, second, options, reverse):
        limit = None
        j = 0
        while j < len(options):
            opt = options[j].upper()
            if opt == b"LIMIT" and j + 2 < len(options):
                if limit is not None:
                    raise Errors.SYNTAX
                try:
                    limit = (string2ll(options[j + 1]), string2ll(options[j + 2]))
                except ValueError:
                    raise Errors.NOT_INT
                j += 3
            else:
                raise Errors.SYNTAX
        parsed, empty = self._parse_bounds(first, second, b"bylex", False)
        zset = self._zset(key)
        if zset is None or empty:
            return []
        pairs = self._range_pairs(zset, parsed, b"bylex", reverse)
        return self._interleave(self._limit_pairs(pairs, limit), withscores=False)

    @command_decorator(b"ZRANGEBYLEX")
    def ZRANGEBYLEX(self, key: bytes, min_: bytes, max_: bytes, *options: bytes):
        return self._legacy_lex_range(key, min_, max_, options, reverse=False)

    @command_decorator(b"ZREVRANGEBYLEX")
    def ZREVRANGEBYLEX(self, key: bytes, max_: bytes, min_: bytes, *options: bytes):
        return self._legacy_lex_range(key, min_, max_, options, reverse=True)

    # ------------------------------------------------------------- counts
    @command_decorator(b"ZCOUNT")
    def ZCOUNT(self, key: bytes, min_: bytes, max_: bytes) -> int:
        lo, lo_open = self._score_bound(min_)
        hi, hi_open = self._score_bound(max_)
        zset = self._zset(key)
        if zset is None:
            return 0
        return len(zset.score_pairs(lo, lo_open, hi, hi_open))

    @command_decorator(b"ZLEXCOUNT")
    def ZLEXCOUNT(self, key: bytes, min_: bytes, max_: bytes) -> int:
        (lo, lo_open, hi, hi_open), empty = self._parse_bounds(
            min_, max_, b"bylex", False
        )
        zset = self._zset(key)
        if zset is None or empty:
            return 0
        return len(zset.member_pairs(lo, lo_open, hi, hi_open))

    # ------------------------------------------------------------ removals
    @command_decorator(b"ZREM")
    def ZREM(self, key: bytes, *members: bytes) -> int:
        if not members:
            raise Errors.arity("zrem")
        zset = self._zset(key)
        if zset is None:
            return 0
        removed = sum(1 for member in members if zset.remove(member))
        self._drop_empty(key, zset)
        return removed

    @command_decorator(b"ZREMRANGEBYRANK")
    def ZREMRANGEBYRANK(self, key: bytes, start: int, stop: int) -> int:
        zset = self._zset(key)
        if zset is None:
            return 0
        removed = zset.remove_rank(start, stop)
        self._drop_empty(key, zset)
        return removed

    @command_decorator(b"ZREMRANGEBYSCORE")
    def ZREMRANGEBYSCORE(self, key: bytes, min_: bytes, max_: bytes) -> int:
        lo, lo_open = self._score_bound(min_)
        hi, hi_open = self._score_bound(max_)
        zset = self._zset(key)
        if zset is None:
            return 0
        removed = zset.remove_score(lo, lo_open, hi, hi_open)
        self._drop_empty(key, zset)
        return removed

    @command_decorator(b"ZREMRANGEBYLEX")
    def ZREMRANGEBYLEX(self, key: bytes, min_: bytes, max_: bytes) -> int:
        (lo, lo_open, hi, hi_open), empty = self._parse_bounds(
            min_, max_, b"bylex", False
        )
        zset = self._zset(key)
        if zset is None or empty:
            return 0
        removed = zset.remove_member(lo, lo_open, hi, hi_open)
        self._drop_empty(key, zset)
        return removed

    # ------------------------------------------------------------- popping
    def _zpop(self, key, count, left):
        if count is not None and count < 0:
            raise Errors.NOT_POSITIVE
        zset = self._zset(key)
        if zset is None or count == 0:
            return []  # redis replies an empty array, never a null one
        if count is None:
            start = stop = 0 if left else -1
        else:
            start, stop = (0, count - 1) if left else (-count, -1)
        taken = self._slice_ranks(zset.pairs(), start, stop)
        if not left:
            taken.reverse()  # ZPOPMAX pops the highest first
        if taken:
            zset.remove_rank(start, stop)
        self._drop_empty(key, zset)
        return self._interleave(taken, withscores=True)

    @command_decorator(b"ZPOPMIN")
    def ZPOPMIN(self, key: bytes, count: int = None) -> list:
        return self._zpop(key, count, left=True)

    @command_decorator(b"ZPOPMAX")
    def ZPOPMAX(self, key: bytes, count: int = None) -> list:
        return self._zpop(key, count, left=False)

    @command_decorator(b"ZRANDMEMBER")
    def ZRANDMEMBER(self, key: bytes, count: int = None, *options: bytes):
        if count is None:
            if options:
                raise Errors.SYNTAX  # WITHSCORES needs a count
            zset = self._zset(key)
            if zset is None or not len(zset):
                return Response.NIL
            return choice(zset.members())

        withscores = False
        for option in options:
            if option.upper() == b"WITHSCORES":
                withscores = True
            else:
                raise Errors.SYNTAX

        zset = self._zset(key)
        if zset is None or not len(zset):
            return []
        members = zset.members()
        if count < 0:
            picked = [choice(members) for _ in range(-count)]
        elif count == 0:
            picked = []
        elif count >= len(members):
            picked = members
        else:
            picked = sample(members, count)
        if not withscores:
            return picked
        out = []
        for member in picked:
            out.append(member)
            out.append(_format_float(zset.score(member)).encode())
        return out

    # ------------------------------------------------------------- stores
    def _parse_zset_op(self, numkeys, rest, command, allow_weights, allow_withscores):
        """Shared numkeys framing: keys[:numkeys], then WEIGHTS and
        AGGREGATE options; *command* names the op for its error text."""
        if numkeys < 1:
            raise Errors.no_keys(command)
        if numkeys > len(rest):
            raise Errors.SYNTAX
        keys = list(rest[:numkeys])
        weights = None
        aggregate = None
        withscores = False
        j = numkeys
        while j < len(rest):
            opt = rest[j].upper()
            if opt == b"WEIGHTS" and allow_weights:
                if weights is not None or j + numkeys >= len(rest):
                    raise Errors.SYNTAX
                weights = []
                for raw in rest[j + 1:j + 1 + numkeys]:
                    try:
                        weights.append(_parse_float(raw))
                    except Error:
                        raise Errors.WEIGHT_FLOAT
                j += 1 + numkeys
            elif opt == b"AGGREGATE" and allow_weights and j + 1 < len(rest):
                if aggregate is not None:
                    raise Errors.SYNTAX
                aggregate = rest[j + 1].upper()
                if aggregate not in (b"SUM", b"MIN", b"MAX"):
                    raise Errors.SYNTAX
                j += 2
            elif opt == b"WITHSCORES" and allow_withscores:
                withscores = True
                j += 1
            else:
                raise Errors.SYNTAX
        if weights is None:
            weights = [1.0] * numkeys
        return keys, weights, aggregate, withscores

    @command_decorator(b"ZUNIONSTORE")
    def ZUNIONSTORE(self, dest: bytes, numkeys: int, *rest: bytes) -> int:
        keys, weights, aggregate, _ = self._parse_zset_op(
            numkeys, rest, "zunionstore", allow_weights=True, allow_withscores=False
        )
        return self._store_aggregate(dest, keys, weights, aggregate, "zunion")

    @command_decorator(b"ZINTERSTORE")
    def ZINTERSTORE(self, dest: bytes, numkeys: int, *rest: bytes) -> int:
        keys, weights, aggregate, _ = self._parse_zset_op(
            numkeys, rest, "zinterstore", allow_weights=True, allow_withscores=False
        )
        return self._store_aggregate(dest, keys, weights, aggregate, "zinter")

    @command_decorator(b"ZDIFFSTORE")
    def ZDIFFSTORE(self, dest: bytes, numkeys: int, *rest: bytes) -> int:
        keys, weights, aggregate, _ = self._parse_zset_op(
            numkeys, rest, "zdiffstore", allow_weights=False, allow_withscores=False
        )
        return self._store_aggregate(dest, keys, weights, aggregate, "zdiff")

    def _store_aggregate(self, dest, keys, weights, aggregate, op):
        result = self._aggregate(keys, weights, aggregate, op)
        if not len(result):
            # redis deletes the destination when the result is empty
            self.data.remove(dest)
            return 0
        self.data[dest] = result
        return len(result)

    @command_decorator(b"ZUNION")
    def ZUNION(self, numkeys: int, *rest: bytes) -> list:
        keys, weights, aggregate, withscores = self._parse_zset_op(
            numkeys, rest, "zunion", allow_weights=True, allow_withscores=True
        )
        result = self._aggregate(keys, weights, aggregate, "zunion")
        return self._interleave(result.pairs(), withscores)

    @command_decorator(b"ZINTER")
    def ZINTER(self, numkeys: int, *rest: bytes) -> list:
        keys, weights, aggregate, withscores = self._parse_zset_op(
            numkeys, rest, "zinter", allow_weights=True, allow_withscores=True
        )
        result = self._aggregate(keys, weights, aggregate, "zinter")
        return self._interleave(result.pairs(), withscores)

    @command_decorator(b"ZDIFF")
    def ZDIFF(self, numkeys: int, *rest: bytes) -> list:
        keys, weights, aggregate, withscores = self._parse_zset_op(
            numkeys, rest, "zdiff", allow_weights=False, allow_withscores=True
        )
        result = self._aggregate(keys, weights, aggregate, "zdiff")
        return self._interleave(result.pairs(), withscores)

    def _aggregate(self, keys, weights, aggregate, op):
        """Union/inter/diff of the stored zsets, built into a fresh ZSet
        (never aliasing a source).  Missing keys behave like empty sets;
        keys of other kinds raise WRONGTYPE while collecting."""
        if aggregate is None:
            aggregate = b"SUM"
        sources = []
        for key in keys:
            sources.append(self._zset(key))

        first = sources[0]
        agg = {}
        if op == "zunion":
            for zset, weight in zip(sources, weights):
                if zset is None:
                    continue
                for score, member in zset.pairs():
                    value = score * weight
                    if member in agg:
                        value = self._combine(agg[member], value, aggregate)
                    agg[member] = value
        elif op == "zinter":
            if first is not None:
                for score, member in first.pairs():
                    value = score * weights[0]
                    for zset, weight in zip(sources[1:], weights[1:]):
                        if zset is None:
                            value = None
                            break
                        score_ = zset.score(member)
                        if score_ is None:
                            value = None
                            break
                        value = self._combine(value, score_ * weight, aggregate)
                    if value is not None:
                        agg[member] = value
        else:  # zdiff: the first set minus the union of the rest
            if first is not None:
                drop = set()
                for zset in sources[1:]:
                    if zset is None:
                        continue
                    for _, member in zset.pairs():
                        drop.add(member)
                agg = {
                    member: score
                    for score, member in first.pairs()
                    if member not in drop
                }

        result = ZSet()
        for member, score in agg.items():
            if score != score:  # NaN aggregation (e.g. weight 0 * inf)
                score = 0.0  # redis folds these to 0
            result.add(member, score)
        return result

    @staticmethod
    def _combine(a, b, aggregate):
        if aggregate == b"MIN":
            return b if b < a else a
        if aggregate == b"MAX":
            return b if b > a else a
        return a + b
