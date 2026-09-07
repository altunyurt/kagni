"""Sorted-set commands: per-command spec battery, one pytest case per scenario."""

from kagni.constants import Response
from kagni.resp import protocolBuilder
from kagni.resp import protocolParser

from .helpers import _commands

def test_zadd_check_zadd_return_value_for_new_members():
    """Check ZADD return value for new members"""
    c = _commands()
    ret = c.ZADD(*[b"k", b"1", b"a", b"2", b"b"])
    assert ret == protocolBuilder(2)

def test_zadd_check_zadd_return_value_for_existing_members():
    """Check ZADD return value for existing members"""
    c = _commands()
    c.ZADD(*[b"k", b"1", b"a"])
    ret = c.ZADD(*[b"k", b"3", b"a", b"4", b"c"])
    assert ret == protocolBuilder(1)

def test_zadd_check_zadd_nx_does_not_update_existing_members():
    """Check ZADD NX does not update existing members"""
    c = _commands()
    c.ZADD(*[b"k", b"1", b"a"])
    ret = c.ZADD(*[b"k", b"NX", b"9", b"a", b"5", b"d"])
    assert ret == protocolBuilder(1)
    assert (c.ZSCORE(b"k", b"a") == b"$1\r\n1\r\n" and c.ZSCORE(b"k", b"d") == b"$1\r\n5\r\n")

def test_zadd_check_zadd_xx_only_updates_existing_members():
    """Check ZADD XX only updates existing members"""
    c = _commands()
    c.ZADD(*[b"k", b"1", b"a"])
    ret = c.ZADD(*[b"k", b"XX", b"9", b"a", b"5", b"d"])
    assert ret == protocolBuilder(0)
    assert (c.ZSCORE(b"k", b"a") == b"$1\r\n9\r\n" and c.ZCARD(b"k") == b":1\r\n")

def test_zadd_check_zadd_xx_on_a_missing_key_creates_nothing():
    """Check ZADD XX on a missing key creates nothing"""
    c = _commands()
    ret = c.ZADD(*[b"nokey", b"XX", b"1", b"a"])
    assert ret == protocolBuilder(0)
    assert (c.EXISTS(b"nokey") == b":0\r\n")

def test_zadd_check_zadd_ch_counts_changed_members():
    """Check ZADD CH counts changed members"""
    c = _commands()
    c.ZADD(*[b"k", b"1", b"a"])
    ret = c.ZADD(*[b"k", b"CH", b"2", b"a", b"7", b"b"])
    assert ret == protocolBuilder(2)

def test_zadd_check_zadd_incr_returns_the_new_score():
    """Check ZADD INCR returns the new score"""
    c = _commands()
    c.ZADD(*[b"k", b"1", b"a"])
    ret = c.ZADD(*[b"k", b"INCR", b"2.5", b"a"])
    parsed = protocolParser(ret)
    assert (parsed == b"3.5")

def test_zadd_check_zadd_gt_blocks_smaller_scores_but_allows_new_members():
    """Check ZADD GT blocks smaller scores but allows new members"""
    c = _commands()
    c.ZADD(*[b"k", b"1", b"a"])
    ret = c.ZADD(*[b"k", b"GT", b"0.5", b"a", b"5", b"new"])
    assert ret == protocolBuilder(1)
    assert (c.ZSCORE(b"k", b"a") == b"$1\r\n1\r\n" and c.ZSCORE(b"k", b"new") == b"$1\r\n5\r\n")

def test_zcard_check_zcard_on_a_populated_key():
    """Check ZCARD on a populated key"""
    c = _commands()
    c.ZADD(*[b"k", b"1", b"a", b"2", b"b", b"3", b"c"])
    ret = c.ZCARD(*[b"k"])
    assert ret == protocolBuilder(3)

def test_zcard_check_zcard_on_a_missing_key():
    """Check ZCARD on a missing key"""
    c = _commands()
    ret = c.ZCARD(*[b"nokey"])
    assert ret == protocolBuilder(0)

def test_zscore_check_zscore_of_a_member():
    """Check ZSCORE of a member"""
    c = _commands()
    c.ZADD(*[b"k", b"1", b"a", b"2", b"b"])
    ret = c.ZSCORE(*[b"k", b"b"])
    assert ret == protocolBuilder(b'2')

def test_zscore_check_zscore_of_a_missing_member():
    """Check ZSCORE of a missing member"""
    c = _commands()
    c.ZADD(*[b"k", b"1", b"a"])
    ret = c.ZSCORE(*[b"k", b"nope"])
    assert ret == protocolBuilder(Response.NIL)

def test_zscore_check_zscore_formats_scores_like_redis():
    """Check ZSCORE formats scores like redis"""
    c = _commands()
    c.ZADD(*[b"k", b"10.5", b"x"])
    ret = c.ZSCORE(*[b"k", b"x"])
    assert ret == protocolBuilder(b'10.5')

def test_zmscore_check_zmscore_replies_one_slot_per_member():
    """Check ZMSCORE replies one slot per member"""
    c = _commands()
    c.ZADD(*[b"k", b"1", b"a", b"2", b"b"])
    ret = c.ZMSCORE(*[b"k", b"a", b"nope", b"b"])
    assert ret == protocolBuilder([b'1', Response.NIL, b'2'])

def test_zincrby_check_zincrby_creates_the_member_when_missing():
    """Check ZINCRBY creates the member when missing"""
    c = _commands()
    ret = c.ZINCRBY(*[b"nokey", b"1.5", b"m"])
    assert ret == protocolBuilder(b'1.5')

def test_zrank_check_zrank_of_a_member():
    """Check ZRANK of a member"""
    c = _commands()
    c.ZADD(*[b"k", b"1", b"a", b"2", b"b", b"3", b"c"])
    ret = c.ZRANK(*[b"k", b"b"])
    assert ret == protocolBuilder(1)

def test_zrank_check_zrank_of_a_missing_member():
    """Check ZRANK of a missing member"""
    c = _commands()
    c.ZADD(*[b"k", b"1", b"a"])
    ret = c.ZRANK(*[b"k", b"nope"])
    assert ret == protocolBuilder(Response.NIL)

def test_zrank_check_zrank_withscore_replies_rank_and_score():
    """Check ZRANK WITHSCORE replies rank and score"""
    c = _commands()
    c.ZADD(*[b"k", b"1", b"a", b"2", b"b", b"3", b"c"])
    ret = c.ZRANK(*[b"k", b"b", b"WITHSCORE"])
    assert ret == protocolBuilder([1, b'2'])

def test_zrevrank_check_zrevrank_counts_from_the_highest_score():
    """Check ZREVRANK counts from the highest score"""
    c = _commands()
    c.ZADD(*[b"k", b"1", b"a", b"2", b"b", b"3", b"c"])
    ret = c.ZREVRANK(*[b"k", b"a"])
    assert ret == protocolBuilder(2)

def test_zrange_check_zrange_over_the_whole_set():
    """Check ZRANGE over the whole set"""
    c = _commands()
    c.ZADD(*[b"k", b"1", b"a", b"2", b"b", b"3", b"c"])
    ret = c.ZRANGE(*[b"k", b"0", b"-1"])
    assert ret == protocolBuilder([b'a', b'b', b'c'])

def test_zrange_check_zrange_withscores_interleaves_scores():
    """Check ZRANGE WITHSCORES interleaves scores"""
    c = _commands()
    c.ZADD(*[b"k", b"1", b"a", b"2", b"b", b"3", b"c"])
    ret = c.ZRANGE(*[b"k", b"0", b"-1", b"WITHSCORES"])
    assert ret == protocolBuilder([b'a', b'1', b'b', b'2', b'c', b'3'])

def test_zrange_check_zrange_with_negative_indexes():
    """Check ZRANGE with negative indexes"""
    c = _commands()
    c.ZADD(*[b"k", b"1", b"a", b"2", b"b", b"3", b"c"])
    ret = c.ZRANGE(*[b"k", b"-2", b"-1"])
    assert ret == protocolBuilder([b'b', b'c'])

def test_zrange_check_zrange_rev_returns_descending():
    """Check ZRANGE REV returns descending"""
    c = _commands()
    c.ZADD(*[b"k", b"1", b"a", b"2", b"b", b"3", b"c"])
    ret = c.ZRANGE(*[b"k", b"0", b"-1", b"REV"])
    assert ret == protocolBuilder([b'c', b'b', b'a'])

def test_zrange_check_zrange_byscore_with_exclusive_bounds():
    """Check ZRANGE BYSCORE with exclusive bounds"""
    c = _commands()
    c.ZADD(*[b"k", b"1", b"a", b"2", b"b", b"3", b"c"])
    ret = c.ZRANGE(*[b"k", b"(1", b"+inf", b"BYSCORE"])
    assert ret == protocolBuilder([b'b', b'c'])

def test_zrange_check_zrange_byscore_rev_takes_max_first():
    """Check ZRANGE BYSCORE REV takes max first"""
    c = _commands()
    c.ZADD(*[b"k", b"1", b"a", b"2", b"b", b"3", b"c"])
    ret = c.ZRANGE(*[b"k", b"3", b"1", b"BYSCORE", b"REV"])
    assert ret == protocolBuilder([b'c', b'b', b'a'])

def test_zrange_check_zrange_byscore_with_limit():
    """Check ZRANGE BYSCORE with LIMIT"""
    c = _commands()
    c.ZADD(*[b"k", b"1", b"a", b"2", b"b", b"3", b"c"])
    ret = c.ZRANGE(*[b"k", b"-inf", b"+inf", b"BYSCORE", b"LIMIT", b"1", b"1"])
    assert ret == protocolBuilder([b'b'])

def test_zrange_check_zrange_on_a_missing_key():
    """Check ZRANGE on a missing key"""
    c = _commands()
    ret = c.ZRANGE(*[b"nokey", b"0", b"-1"])
    assert ret == protocolBuilder([])

def test_zrange_check_equal_scores_order_by_member_bytes():
    """Check equal scores order by member bytes"""
    c = _commands()
    c.ZADD(*[b"k", b"0", b"c", b"0", b"a", b"0", b"b"])
    ret = c.ZRANGE(*[b"k", b"0", b"-1"])
    assert ret == protocolBuilder([b'a', b'b', b'c'])

def test_zcount_check_zcount_within_a_score_window():
    """Check ZCOUNT within a score window"""
    c = _commands()
    c.ZADD(*[b"k", b"1", b"a", b"2", b"b", b"3", b"c"])
    ret = c.ZCOUNT(*[b"k", b"1", b"2"])
    assert ret == protocolBuilder(2)

def test_zcount_check_zcount_with_exclusive_bounds():
    """Check ZCOUNT with exclusive bounds"""
    c = _commands()
    c.ZADD(*[b"k", b"1", b"a", b"2", b"b", b"3", b"c"])
    ret = c.ZCOUNT(*[b"k", b"(1", b"+inf"])
    assert ret == protocolBuilder(2)

def test_zrem_check_zrem_removes_members():
    """Check ZREM removes members"""
    c = _commands()
    c.ZADD(*[b"k", b"1", b"a", b"2", b"b"])
    ret = c.ZREM(*[b"k", b"a", b"nope"])
    assert ret == protocolBuilder(1)

def test_zrem_check_zrem_of_the_last_member_deletes_the_key():
    """Check ZREM of the last member deletes the key"""
    c = _commands()
    c.ZADD(*[b"k", b"1", b"a"])
    ret = c.ZREM(*[b"k", b"a"])
    assert ret == protocolBuilder(1)
    assert (c.EXISTS(b"k") == b":0\r\n")

def test_zpopmin_check_zpopmin_pops_the_lowest_member():
    """Check ZPOPMIN pops the lowest member"""
    c = _commands()
    c.ZADD(*[b"k", b"1", b"a", b"2", b"b"])
    ret = c.ZPOPMIN(*[b"k"])
    assert ret == protocolBuilder([b'a', b'1'])

def test_zpopmax_check_zpopmax_with_a_count_pops_highest_first():
    """Check ZPOPMAX with a count pops highest first"""
    c = _commands()
    c.ZADD(*[b"k", b"1", b"a", b"2", b"b", b"3", b"c"])
    ret = c.ZPOPMAX(*[b"k", b"2"])
    assert ret == protocolBuilder([b'c', b'3', b'b', b'2'])

def test_zpopmin_check_zpopmin_on_a_missing_key():
    """Check ZPOPMIN on a missing key"""
    c = _commands()
    ret = c.ZPOPMIN(*[b"nokey"])
    assert ret == protocolBuilder([])

def test_zpopmin_check_zpopmin_empties_and_deletes_the_key():
    """Check ZPOPMIN empties and deletes the key"""
    c = _commands()
    c.ZADD(*[b"k", b"1", b"a"])
    ret = c.ZPOPMIN(*[b"k", b"5"])
    assert ret == protocolBuilder([b'a', b'1'])
    assert (c.EXISTS(b"k") == b":0\r\n")

def test_zremrangebyrank_check_zremrangebyrank_removes_a_rank_window():
    """Check ZREMRANGEBYRANK removes a rank window"""
    c = _commands()
    c.ZADD(*[b"k", b"1", b"a", b"2", b"b", b"3", b"c"])
    ret = c.ZREMRANGEBYRANK(*[b"k", b"0", b"1"])
    assert ret == protocolBuilder(2)
    assert (c.ZRANGE(b"k", b"0", b"-1") == b"*1\r\n$1\r\nc\r\n")

def test_zremrangebyscore_check_zremrangebyscore_removes_a_score_window():
    """Check ZREMRANGEBYSCORE removes a score window"""
    c = _commands()
    c.ZADD(*[b"k", b"1", b"a", b"2", b"b", b"3", b"c"])
    ret = c.ZREMRANGEBYSCORE(*[b"k", b"2", b"+inf"])
    assert ret == protocolBuilder(2)
    assert (c.ZCARD(b"k") == b":1\r\n")

def test_zrangebylex_check_zrangebylex_ordering():
    """Check ZRANGEBYLEX ordering"""
    c = _commands()
    c.ZADD(*[b"k", b"0", b"d", b"0", b"a", b"0", b"c", b"0", b"b"])
    ret = c.ZRANGEBYLEX(*[b"k", b"-", b"+"])
    assert ret == protocolBuilder([b'a', b'b', b'c', b'd'])

def test_zrangebylex_check_zrangebylex_window_with_exclusive_max():
    """Check ZRANGEBYLEX window with exclusive max"""
    c = _commands()
    c.ZADD(*[b"k", b"0", b"a", b"0", b"b", b"0", b"c", b"0", b"d"])
    ret = c.ZRANGEBYLEX(*[b"k", b"[b", b"(d"])
    assert ret == protocolBuilder([b'b', b'c'])

def test_zrevrangebylex_check_zrevrangebylex_returns_descending():
    """Check ZREVRANGEBYLEX returns descending"""
    c = _commands()
    c.ZADD(*[b"k", b"0", b"a", b"0", b"b", b"0", b"c", b"0", b"d"])
    ret = c.ZREVRANGEBYLEX(*[b"k", b"+", b"-"])
    assert ret == protocolBuilder([b'd', b'c', b'b', b'a'])

def test_zlexcount_check_zlexcount_counts_the_window():
    """Check ZLEXCOUNT counts the window"""
    c = _commands()
    c.ZADD(*[b"k", b"0", b"a", b"0", b"b", b"0", b"c", b"0", b"d"])
    ret = c.ZLEXCOUNT(*[b"k", b"[b", b"+"])
    assert ret == protocolBuilder(3)

def test_zremrangebylex_check_zremrangebylex_removes_the_window():
    """Check ZREMRANGEBYLEX removes the window"""
    c = _commands()
    c.ZADD(*[b"k", b"0", b"a", b"0", b"b", b"0", b"c", b"0", b"d"])
    ret = c.ZREMRANGEBYLEX(*[b"k", b"[a", b"[b"])
    assert ret == protocolBuilder(2)
    assert (c.ZRANGEBYLEX(b"k", b"-", b"+") == b"*2\r\n$1\r\nc\r\n$1\r\nd\r\n")

def test_zunionstore_check_zunionstore_sums_scores_of_shared_members():
    """Check ZUNIONSTORE sums scores of shared members"""
    c = _commands()
    c.ZADD(*[b"a", b"1", b"x", b"2", b"y"])
    c.ZADD(*[b"b", b"3", b"y", b"4", b"z"])
    ret = c.ZUNIONSTORE(*[b"dst", b"2", b"a", b"b"])
    assert ret == protocolBuilder(3)
    assert (c.ZRANGE(b"dst", b"0", b"-1", b"WITHSCORES") == b"*6\r\n$1\r\nx\r\n$1\r\n1\r\n$1\r\nz\r\n$1\r\n4\r\n$1\r\ny\r\n$1\r\n5\r\n")

def test_zinterstore_check_zinterstore_keeps_only_shared_members():
    """Check ZINTERSTORE keeps only shared members"""
    c = _commands()
    c.ZADD(*[b"a", b"1", b"x", b"2", b"y"])
    c.ZADD(*[b"b", b"3", b"y", b"4", b"z"])
    ret = c.ZINTERSTORE(*[b"dst", b"2", b"a", b"b"])
    assert ret == protocolBuilder(1)
    assert (c.ZSCORE(b"dst", b"y") == b"$1\r\n5\r\n")

def test_zdiffstore_check_zdiffstore_keeps_the_first_set_minus_the_rest():
    """Check ZDIFFSTORE keeps the first set minus the rest"""
    c = _commands()
    c.ZADD(*[b"a", b"1", b"x", b"2", b"y"])
    c.ZADD(*[b"b", b"3", b"y", b"4", b"z"])
    ret = c.ZDIFFSTORE(*[b"dst", b"2", b"a", b"b"])
    assert ret == protocolBuilder(1)
    assert (c.ZSCORE(b"dst", b"x") == b"$1\r\n1\r\n")

def test_zunionstore_check_zunionstore_with_weights_and_aggregate_min():
    """Check ZUNIONSTORE with WEIGHTS and AGGREGATE MIN"""
    c = _commands()
    c.ZADD(*[b"a", b"1", b"x", b"2", b"y"])
    c.ZADD(*[b"b", b"3", b"y", b"4", b"z"])
    ret = c.ZUNIONSTORE(*[b"dst", b"2", b"a", b"b", b"WEIGHTS", b"2", b"3", b"AGGREGATE", b"MIN"])
    assert ret == protocolBuilder(3)
    assert (c.ZSCORE(b"dst", b"y") == b"$1\r\n4\r\n")

def test_zunionstore_check_zunionstore_of_an_empty_result_deletes_the_destination():
    """Check ZUNIONSTORE of an empty result deletes the destination"""
    c = _commands()
    c.SET(*[b"dst", b"old"])
    ret = c.ZUNIONSTORE(*[b"dst", b"1", b"missing"])
    assert ret == protocolBuilder(0)
    assert (c.EXISTS(b"dst") == b":0\r\n")

def test_zunion_check_zunion_reads_with_withscores():
    """Check ZUNION reads with WITHSCORES"""
    c = _commands()
    c.ZADD(*[b"a", b"1", b"x", b"2", b"y"])
    ret = c.ZUNION(*[b"1", b"a", b"WITHSCORES"])
    assert ret == protocolBuilder([b'x', b'1', b'y', b'2'])

def test_zrandmember_check_zrandmember_picks_an_existing_member():
    """Check ZRANDMEMBER picks an existing member"""
    c = _commands()
    c.ZADD(*[b"k", b"1", b"a", b"2", b"b", b"3", b"c"])
    ret = c.ZRANDMEMBER(*[b"k"])
    parsed = protocolParser(ret)
    assert (parsed in (b"a", b"b", b"c"))
