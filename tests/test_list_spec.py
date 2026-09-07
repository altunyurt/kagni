"""List commands: per-command spec battery, one pytest case per scenario."""

from kagni.constants import Response
from kagni.resp import protocolBuilder

from .helpers import _commands

def test_lpush_check_lpush_on_missing_key_creates_the_list():
    """Check LPUSH on missing key creates the list"""
    c = _commands()
    ret = c.LPUSH(*[b"k", b"a"])
    assert ret == protocolBuilder(1)
    assert (list(c.data[b"k"]) == [b"a"])

def test_lpush_check_lpush_return_value_for_multiple_values():
    """Check LPUSH return value for multiple values"""
    c = _commands()
    ret = c.LPUSH(*[b"k", b"a", b"b", b"c"])
    assert ret == protocolBuilder(3)
    assert (list(c.data[b"k"]) == [b"c", b"b", b"a"])

def test_lpush_check_lpush_ordering_when_pushing_onto_an_existing_list():
    """Check LPUSH ordering when pushing onto an existing list"""
    c = _commands()
    c.LPUSH(*[b"k", b"a", b"b"])
    ret = c.LPUSH(*[b"k", b"c", b"d"])
    assert ret == protocolBuilder(4)
    assert (list(c.data[b"k"]) == [b"d", b"c", b"b", b"a"])

def test_rpush_check_rpush_on_missing_key_creates_the_list():
    """Check RPUSH on missing key creates the list"""
    c = _commands()
    ret = c.RPUSH(*[b"k", b"a"])
    assert ret == protocolBuilder(1)
    assert (list(c.data[b"k"]) == [b"a"])

def test_rpush_check_rpush_return_value_and_ordering_for_multiple_values():
    """Check RPUSH return value and ordering for multiple values"""
    c = _commands()
    ret = c.RPUSH(*[b"k", b"a", b"b", b"c"])
    assert ret == protocolBuilder(3)
    assert (list(c.data[b"k"]) == [b"a", b"b", b"c"])

def test_rpush_check_rpush_appends_after_lpush():
    """Check RPUSH appends after LPUSH"""
    c = _commands()
    c.LPUSH(*[b"k", b"a", b"b"])
    ret = c.RPUSH(*[b"k", b"c", b"d"])
    assert ret == protocolBuilder(4)
    assert (list(c.data[b"k"]) == [b"b", b"a", b"c", b"d"])

def test_lpushx_check_lpushx_on_a_missing_key_is_a_no_op():
    """Check LPUSHX on a missing key is a no-op"""
    c = _commands()
    ret = c.LPUSHX(*[b"k", b"a"])
    assert ret == protocolBuilder(0)
    assert (b"k" not in c.data)

def test_lpushx_check_lpushx_return_value_on_an_existing_list():
    """Check LPUSHX return value on an existing list"""
    c = _commands()
    c.LPUSH(*[b"k", b"a", b"b"])
    ret = c.LPUSHX(*[b"k", b"c"])
    assert ret == protocolBuilder(3)
    assert (list(c.data[b"k"]) == [b"c", b"b", b"a"])

def test_rpushx_check_rpushx_on_a_missing_key_is_a_no_op():
    """Check RPUSHX on a missing key is a no-op"""
    c = _commands()
    ret = c.RPUSHX(*[b"k", b"a"])
    assert ret == protocolBuilder(0)
    assert (b"k" not in c.data)

def test_rpushx_check_rpushx_return_value_on_an_existing_list():
    """Check RPUSHX return value on an existing list"""
    c = _commands()
    c.RPUSH(*[b"k", b"a", b"b"])
    ret = c.RPUSHX(*[b"k", b"c"])
    assert ret == protocolBuilder(3)
    assert (list(c.data[b"k"]) == [b"a", b"b", b"c"])

def test_llen_check_llen_on_a_missing_key():
    """Check LLEN on a missing key"""
    c = _commands()
    ret = c.LLEN(*[b"k"])
    assert ret == protocolBuilder(0)

def test_llen_check_llen_return_value():
    """Check LLEN return value"""
    c = _commands()
    c.RPUSH(*[b"k", b"a", b"b", b"c"])
    ret = c.LLEN(*[b"k"])
    assert ret == protocolBuilder(3)

def test_lrange_check_lrange_on_a_missing_key():
    """Check LRANGE on a missing key"""
    c = _commands()
    ret = c.LRANGE(*[b"k", b"0", b"-1"])
    assert ret == protocolBuilder([])

def test_lrange_check_lrange_full_range():
    """Check LRANGE full range"""
    c = _commands()
    c.RPUSH(*[b"k", b"a", b"b", b"c", b"d", b"e"])
    ret = c.LRANGE(*[b"k", b"0", b"-1"])
    assert ret == protocolBuilder([b'a', b'b', b'c', b'd', b'e'])

def test_lrange_check_lrange_positive_sub_range():
    """Check LRANGE positive sub-range"""
    c = _commands()
    c.RPUSH(*[b"k", b"a", b"b", b"c", b"d", b"e"])
    ret = c.LRANGE(*[b"k", b"1", b"3"])
    assert ret == protocolBuilder([b'b', b'c', b'd'])

def test_lrange_check_lrange_negative_offsets():
    """Check LRANGE negative offsets"""
    c = _commands()
    c.RPUSH(*[b"k", b"a", b"b", b"c", b"d", b"e"])
    ret = c.LRANGE(*[b"k", b"-3", b"-1"])
    assert ret == protocolBuilder([b'c', b'd', b'e'])

def test_lrange_check_lrange_negative_start_with_positive_end():
    """Check LRANGE negative start with positive end"""
    c = _commands()
    c.RPUSH(*[b"k", b"a", b"b", b"c", b"d", b"e"])
    ret = c.LRANGE(*[b"k", b"-2", b"10"])
    assert ret == protocolBuilder([b'd', b'e'])

def test_lrange_check_lrange_with_start_greater_than_end():
    """Check LRANGE with start greater than end"""
    c = _commands()
    c.RPUSH(*[b"k", b"a", b"b", b"c", b"d", b"e"])
    ret = c.LRANGE(*[b"k", b"4", b"2"])
    assert ret == protocolBuilder([])

def test_lrange_check_lrange_clamps_end_beyond_the_list():
    """Check LRANGE clamps end beyond the list"""
    c = _commands()
    c.RPUSH(*[b"k", b"a", b"b", b"c", b"d", b"e"])
    ret = c.LRANGE(*[b"k", b"3", b"99"])
    assert ret == protocolBuilder([b'd', b'e'])

def test_lrange_check_lrange_with_start_beyond_the_list():
    """Check LRANGE with start beyond the list"""
    c = _commands()
    c.RPUSH(*[b"k", b"a", b"b", b"c", b"d", b"e"])
    ret = c.LRANGE(*[b"k", b"99", b"100"])
    assert ret == protocolBuilder([])

def test_lrange_check_lrange_with_very_negative_end():
    """Check LRANGE with very negative end"""
    c = _commands()
    c.RPUSH(*[b"k", b"a", b"b", b"c", b"d", b"e"])
    ret = c.LRANGE(*[b"k", b"0", b"-99"])
    assert ret == protocolBuilder([])

def test_lindex_check_lindex_on_a_missing_key():
    """Check LINDEX on a missing key"""
    c = _commands()
    ret = c.LINDEX(*[b"k", b"0"])
    assert ret == protocolBuilder(Response.NIL)

def test_lindex_check_lindex_first_element():
    """Check LINDEX first element"""
    c = _commands()
    c.RPUSH(*[b"k", b"a", b"b", b"c"])
    ret = c.LINDEX(*[b"k", b"0"])
    assert ret == protocolBuilder(b'a')

def test_lindex_check_lindex_last_element_via_negative_index():
    """Check LINDEX last element via negative index"""
    c = _commands()
    c.RPUSH(*[b"k", b"a", b"b", b"c"])
    ret = c.LINDEX(*[b"k", b"-1"])
    assert ret == protocolBuilder(b'c')

def test_lindex_check_lindex_middle_element():
    """Check LINDEX middle element"""
    c = _commands()
    c.RPUSH(*[b"k", b"a", b"b", b"c"])
    ret = c.LINDEX(*[b"k", b"1"])
    assert ret == protocolBuilder(b'b')

def test_lindex_check_lindex_out_of_range_returns_nil():
    """Check LINDEX out of range returns nil"""
    c = _commands()
    c.RPUSH(*[b"k", b"a", b"b", b"c"])
    ret = c.LINDEX(*[b"k", b"99"])
    assert ret == protocolBuilder(Response.NIL)

def test_lindex_check_lindex_negative_out_of_range_returns_nil():
    """Check LINDEX negative out of range returns nil"""
    c = _commands()
    c.RPUSH(*[b"k", b"a", b"b", b"c"])
    ret = c.LINDEX(*[b"k", b"-99"])
    assert ret == protocolBuilder(Response.NIL)

def test_lset_check_lset_updates_an_element():
    """Check LSET updates an element"""
    c = _commands()
    c.RPUSH(*[b"k", b"a", b"b", b"c"])
    ret = c.LSET(*[b"k", b"1", b"X"])
    assert ret == protocolBuilder(Response.OK)
    assert (list(c.data[b"k"]) == [b"a", b"X", b"c"])

def test_lset_check_lset_with_negative_index_updates_the_tail():
    """Check LSET with negative index updates the tail"""
    c = _commands()
    c.RPUSH(*[b"k", b"a", b"b", b"c"])
    ret = c.LSET(*[b"k", b"-1", b"Z"])
    assert ret == protocolBuilder(Response.OK)
    assert (list(c.data[b"k"]) == [b"a", b"b", b"Z"])

def test_ltrim_check_ltrim_on_a_missing_key():
    """Check LTRIM on a missing key"""
    c = _commands()
    ret = c.LTRIM(*[b"k", b"0", b"-1"])
    assert ret == protocolBuilder(Response.OK)

def test_ltrim_check_ltrim_keeps_the_middle_of_the_list():
    """Check LTRIM keeps the middle of the list"""
    c = _commands()
    c.RPUSH(*[b"k", b"a", b"b", b"c", b"d", b"e"])
    ret = c.LTRIM(*[b"k", b"1", b"3"])
    assert ret == protocolBuilder(Response.OK)
    assert (list(c.data[b"k"]) == [b"b", b"c", b"d"])

def test_ltrim_check_ltrim_clamps_the_end_beyond_the_list():
    """Check LTRIM clamps the end beyond the list"""
    c = _commands()
    c.RPUSH(*[b"k", b"a", b"b", b"c", b"d", b"e"])
    ret = c.LTRIM(*[b"k", b"3", b"99"])
    assert ret == protocolBuilder(Response.OK)
    assert (list(c.data[b"k"]) == [b"d", b"e"])

def test_ltrim_check_ltrim_with_negative_offsets():
    """Check LTRIM with negative offsets"""
    c = _commands()
    c.RPUSH(*[b"k", b"a", b"b", b"c", b"d", b"e"])
    ret = c.LTRIM(*[b"k", b"-3", b"-2"])
    assert ret == protocolBuilder(Response.OK)
    assert (list(c.data[b"k"]) == [b"c", b"d"])

def test_ltrim_check_ltrim_deleting_the_whole_list_removes_the_key():
    """Check LTRIM deleting the whole list removes the key"""
    c = _commands()
    c.RPUSH(*[b"k", b"a", b"b"])
    ret = c.LTRIM(*[b"k", b"5", b"10"])
    assert ret == protocolBuilder(Response.OK)
    assert (b"k" not in c.data)

def test_ltrim_check_ltrim_with_start_greater_than_end_removes_the_key():
    """Check LTRIM with start greater than end removes the key"""
    c = _commands()
    c.RPUSH(*[b"k", b"a", b"b"])
    ret = c.LTRIM(*[b"k", b"3", b"1"])
    assert ret == protocolBuilder(Response.OK)
    assert (b"k" not in c.data)

def test_ltrim_check_ltrim_to_the_full_list_is_a_no_op():
    """Check LTRIM to the full list is a no-op"""
    c = _commands()
    c.RPUSH(*[b"k", b"a", b"b"])
    ret = c.LTRIM(*[b"k", b"0", b"-1"])
    assert ret == protocolBuilder(Response.OK)
    assert (list(c.data[b"k"]) == [b"a", b"b"])

def test_lpop_check_lpop_on_a_missing_key():
    """Check LPOP on a missing key"""
    c = _commands()
    ret = c.LPOP(*[b"k"])
    assert ret == protocolBuilder(Response.NIL)

def test_lpop_check_lpop_with_count_on_a_missing_key_returns_null_array():
    """Check LPOP with count on a missing key returns null array"""
    c = _commands()
    ret = c.LPOP(*[b"k", b"5"])
    assert ret == protocolBuilder(Response.NIL_ARRAY)

def test_lpop_check_lpop_pops_from_the_head():
    """Check LPOP pops from the head"""
    c = _commands()
    c.RPUSH(*[b"k", b"a", b"b"])
    ret = c.LPOP(*[b"k"])
    assert ret == protocolBuilder(b'a')
    assert (list(c.data[b"k"]) == [b"b"])

def test_lpop_check_lpop_removing_the_last_element_deletes_the_key():
    """Check LPOP removing the last element deletes the key"""
    c = _commands()
    c.RPUSH(*[b"k", b"a"])
    ret = c.LPOP(*[b"k"])
    assert ret == protocolBuilder(b'a')
    assert (b"k" not in c.data)

def test_lpop_check_lpop_with_count_pops_head_first():
    """Check LPOP with count pops head-first"""
    c = _commands()
    c.RPUSH(*[b"k", b"a", b"b", b"c", b"d"])
    ret = c.LPOP(*[b"k", b"2"])
    assert ret == protocolBuilder([b'a', b'b'])
    assert (list(c.data[b"k"]) == [b"c", b"d"])

def test_lpop_check_lpop_with_count_bigger_than_the_list_pops_everything():
    """Check LPOP with count bigger than the list pops everything"""
    c = _commands()
    c.RPUSH(*[b"k", b"a", b"b"])
    ret = c.LPOP(*[b"k", b"10"])
    assert ret == protocolBuilder([b'a', b'b'])
    assert (b"k" not in c.data)

def test_lpop_check_lpop_with_count_zero_returns_an_empty_array():
    """Check LPOP with count zero returns an empty array"""
    c = _commands()
    c.RPUSH(*[b"k", b"a", b"b"])
    ret = c.LPOP(*[b"k", b"0"])
    assert ret == protocolBuilder([])
    assert (list(c.data[b"k"]) == [b"a", b"b"])

def test_rpop_check_rpop_pops_from_the_tail():
    """Check RPOP pops from the tail"""
    c = _commands()
    c.RPUSH(*[b"k", b"a", b"b"])
    ret = c.RPOP(*[b"k"])
    assert ret == protocolBuilder(b'b')
    assert (list(c.data[b"k"]) == [b"a"])

def test_rpop_check_rpop_with_count_returns_tail_first():
    """Check RPOP with count returns tail-first"""
    c = _commands()
    c.RPUSH(*[b"k", b"a", b"b", b"c", b"d"])
    ret = c.RPOP(*[b"k", b"2"])
    assert ret == protocolBuilder([b'd', b'c'])
    assert (list(c.data[b"k"]) == [b"a", b"b"])

def test_rpop_check_rpop_with_count_bigger_than_the_list_pops_everything():
    """Check RPOP with count bigger than the list pops everything"""
    c = _commands()
    c.RPUSH(*[b"k", b"a", b"b"])
    ret = c.RPOP(*[b"k", b"10"])
    assert ret == protocolBuilder([b'b', b'a'])
    assert (b"k" not in c.data)

def test_rpop_check_rpop_on_a_missing_key():
    """Check RPOP on a missing key"""
    c = _commands()
    ret = c.RPOP(*[b"k"])
    assert ret == protocolBuilder(Response.NIL)

def test_lrem_check_lrem_on_a_missing_key():
    """Check LREM on a missing key"""
    c = _commands()
    ret = c.LREM(*[b"k", b"0", b"a"])
    assert ret == protocolBuilder(0)

def test_lrem_check_lrem_with_count_zero_removes_all_matches():
    """Check LREM with count zero removes all matches"""
    c = _commands()
    c.RPUSH(*[b"k", b"a", b"b", b"a", b"c", b"a"])
    ret = c.LREM(*[b"k", b"0", b"a"])
    assert ret == protocolBuilder(3)
    assert (list(c.data[b"k"]) == [b"b", b"c"])

def test_lrem_check_lrem_with_positive_count_removes_from_the_head():
    """Check LREM with positive count removes from the head"""
    c = _commands()
    c.RPUSH(*[b"k", b"a", b"b", b"a", b"c", b"a"])
    ret = c.LREM(*[b"k", b"1", b"a"])
    assert ret == protocolBuilder(1)
    assert (list(c.data[b"k"]) == [b"b", b"a", b"c", b"a"])

def test_lrem_check_lrem_with_negative_count_removes_from_the_tail():
    """Check LREM with negative count removes from the tail"""
    c = _commands()
    c.RPUSH(*[b"k", b"a", b"b", b"a", b"c", b"a"])
    ret = c.LREM(*[b"k", b"-1", b"a"])
    assert ret == protocolBuilder(1)
    assert (list(c.data[b"k"]) == [b"a", b"b", b"a", b"c"])

def test_lrem_check_lrem_with_negative_count_removes_several_from_the_tail():
    """Check LREM with negative count removes several from the tail"""
    c = _commands()
    c.RPUSH(*[b"k", b"a", b"b", b"a", b"c", b"a"])
    ret = c.LREM(*[b"k", b"-2", b"a"])
    assert ret == protocolBuilder(2)
    assert (list(c.data[b"k"]) == [b"a", b"b", b"c"])

def test_lrem_check_lrem_with_no_matches():
    """Check LREM with no matches"""
    c = _commands()
    c.RPUSH(*[b"k", b"a", b"b"])
    ret = c.LREM(*[b"k", b"0", b"zz"])
    assert ret == protocolBuilder(0)
    assert (list(c.data[b"k"]) == [b"a", b"b"])

def test_lrem_check_lrem_removing_everything_deletes_the_key():
    """Check LREM removing everything deletes the key"""
    c = _commands()
    c.RPUSH(*[b"k", b"a", b"a"])
    ret = c.LREM(*[b"k", b"0", b"a"])
    assert ret == protocolBuilder(2)
    assert (b"k" not in c.data)

def test_linsert_check_linsert_on_a_missing_key():
    """Check LINSERT on a missing key"""
    c = _commands()
    ret = c.LINSERT(*[b"k", b"BEFORE", b"a", b"X"])
    assert ret == protocolBuilder(0)

def test_linsert_check_linsert_with_a_missing_pivot():
    """Check LINSERT with a missing pivot"""
    c = _commands()
    c.RPUSH(*[b"k", b"a", b"b"])
    ret = c.LINSERT(*[b"k", b"BEFORE", b"zz", b"X"])
    assert ret == protocolBuilder(-1)

def test_linsert_check_linsert_before_an_element():
    """Check LINSERT BEFORE an element"""
    c = _commands()
    c.RPUSH(*[b"k", b"a", b"b"])
    ret = c.LINSERT(*[b"k", b"BEFORE", b"b", b"X"])
    assert ret == protocolBuilder(3)
    assert (list(c.data[b"k"]) == [b"a", b"X", b"b"])

def test_linsert_check_linsert_after_an_element():
    """Check LINSERT AFTER an element"""
    c = _commands()
    c.RPUSH(*[b"k", b"a", b"b"])
    ret = c.LINSERT(*[b"k", b"AFTER", b"a", b"X"])
    assert ret == protocolBuilder(3)
    assert (list(c.data[b"k"]) == [b"a", b"X", b"b"])

def test_linsert_check_linsert_before_the_head_element():
    """Check LINSERT BEFORE the head element"""
    c = _commands()
    c.RPUSH(*[b"k", b"a"])
    ret = c.LINSERT(*[b"k", b"BEFORE", b"a", b"X"])
    assert ret == protocolBuilder(2)
    assert (list(c.data[b"k"]) == [b"X", b"a"])

def test_linsert_check_linsert_is_case_insensitive_on_the_where_argument():
    """Check LINSERT is case-insensitive on the where argument"""
    c = _commands()
    c.RPUSH(*[b"k", b"a", b"b"])
    ret = c.LINSERT(*[b"k", b"after", b"a", b"X"])
    assert ret == protocolBuilder(3)
    assert (list(c.data[b"k"]) == [b"a", b"X", b"b"])

def test_lmove_check_lmove_on_a_missing_source():
    """Check LMOVE on a missing source"""
    c = _commands()
    ret = c.LMOVE(*[b"src", b"dst", b"LEFT", b"LEFT"])
    assert ret == protocolBuilder(Response.NIL)
    assert (b"dst" not in c.data)

def test_lmove_check_lmove_left_left_moves_the_head_and_replies_with_it():
    """Check LMOVE LEFT LEFT moves the head and replies with it"""
    c = _commands()
    c.RPUSH(*[b"src", b"a", b"b"])
    ret = c.LMOVE(*[b"src", b"dst", b"LEFT", b"LEFT"])
    assert ret == protocolBuilder(b'a')
    assert (list(c.data[b"src"]) == [b"b"] and list(c.data[b"dst"]) == [b"a"])

def test_lmove_check_lmove_right_right_moves_the_tail_to_the_destination_ta():
    """Check LMOVE RIGHT RIGHT moves the tail to the destination tail"""
    c = _commands()
    c.RPUSH(*[b"src", b"a", b"b", b"c"])
    c.RPUSH(*[b"dst", b"x"])
    ret = c.LMOVE(*[b"src", b"dst", b"RIGHT", b"RIGHT"])
    assert ret == protocolBuilder(b'c')
    assert (list(c.data[b"src"]) == [b"a", b"b"] and list(c.data[b"dst"]) == [b"x", b"c"])

def test_lmove_check_lmove_right_left_pushes_onto_the_destination_head():
    """Check LMOVE RIGHT LEFT pushes onto the destination head"""
    c = _commands()
    c.RPUSH(*[b"src", b"a", b"b"])
    c.RPUSH(*[b"dst", b"x"])
    ret = c.LMOVE(*[b"src", b"dst", b"RIGHT", b"LEFT"])
    assert ret == protocolBuilder(b'b')
    assert (list(c.data[b"src"]) == [b"a"] and list(c.data[b"dst"]) == [b"b", b"x"])

def test_lmove_check_lmove_is_case_insensitive_on_the_sides():
    """Check LMOVE is case-insensitive on the sides"""
    c = _commands()
    c.RPUSH(*[b"src", b"a"])
    ret = c.LMOVE(*[b"src", b"dst", b"left", b"RIGHT"])
    assert ret == protocolBuilder(b'a')

def test_lmove_check_lmove_moving_the_last_element_deletes_the_source():
    """Check LMOVE moving the last element deletes the source"""
    c = _commands()
    c.RPUSH(*[b"src", b"a"])
    ret = c.LMOVE(*[b"src", b"dst", b"LEFT", b"LEFT"])
    assert ret == protocolBuilder(b'a')
    assert (b"src" not in c.data and list(c.data[b"dst"]) == [b"a"])

def test_lmove_check_lmove_rotates_when_source_and_destination_are_the_same():
    """Check LMOVE rotates when source and destination are the same"""
    c = _commands()
    c.RPUSH(*[b"k", b"a", b"b", b"c"])
    ret = c.LMOVE(*[b"k", b"k", b"LEFT", b"RIGHT"])
    assert ret == protocolBuilder(b'a')
    assert (list(c.data[b"k"]) == [b"b", b"c", b"a"])

def test_lmove_check_lmove_right_left_on_the_same_key_rotates_the_other_way():
    """Check LMOVE RIGHT LEFT on the same key rotates the other way"""
    c = _commands()
    c.RPUSH(*[b"k", b"a", b"b", b"c"])
    ret = c.LMOVE(*[b"k", b"k", b"RIGHT", b"LEFT"])
    assert ret == protocolBuilder(b'c')
    assert (list(c.data[b"k"]) == [b"c", b"a", b"b"])

def test_rpoplpush_check_rpoplpush_on_a_missing_source():
    """Check RPOPLPUSH on a missing source"""
    c = _commands()
    ret = c.RPOPLPUSH(*[b"src", b"dst"])
    assert ret == protocolBuilder(Response.NIL)

def test_rpoplpush_check_rpoplpush_moves_the_tail_to_the_destination_head():
    """Check RPOPLPUSH moves the tail to the destination head"""
    c = _commands()
    c.RPUSH(*[b"src", b"a", b"b", b"c"])
    c.RPUSH(*[b"dst", b"x"])
    ret = c.RPOPLPUSH(*[b"src", b"dst"])
    assert ret == protocolBuilder(b'c')
    assert (list(c.data[b"src"]) == [b"a", b"b"] and list(c.data[b"dst"]) == [b"c", b"x"])

def test_rpoplpush_check_rpoplpush_rotates_when_source_and_destination_match():
    """Check RPOPLPUSH rotates when source and destination match"""
    c = _commands()
    c.RPUSH(*[b"k", b"a", b"b", b"c"])
    ret = c.RPOPLPUSH(*[b"k", b"k"])
    assert ret == protocolBuilder(b'c')
    assert (list(c.data[b"k"]) == [b"c", b"a", b"b"])

def test_lpos_check_lpos_on_a_missing_key():
    """Check LPOS on a missing key"""
    c = _commands()
    ret = c.LPOS(*[b"k", b"a"])
    assert ret == protocolBuilder(Response.NIL)

def test_lpos_check_lpos_on_a_missing_key_with_count_returns_an_empty_arra():
    """Check LPOS on a missing key with COUNT returns an empty array"""
    c = _commands()
    ret = c.LPOS(*[b"k", b"a", b"COUNT", b"0"])
    assert ret == protocolBuilder([])

def test_lpos_check_lpos_finds_the_first_match():
    """Check LPOS finds the first match"""
    c = _commands()
    c.RPUSH(*[b"k", b"a", b"b", b"a", b"c", b"a"])
    ret = c.LPOS(*[b"k", b"a"])
    assert ret == protocolBuilder(0)

def test_lpos_check_lpos_with_no_match():
    """Check LPOS with no match"""
    c = _commands()
    c.RPUSH(*[b"k", b"a", b"b", b"a", b"c", b"a"])
    ret = c.LPOS(*[b"k", b"zz"])
    assert ret == protocolBuilder(Response.NIL)

def test_lpos_check_lpos_with_rank_finds_the_nth_match():
    """Check LPOS with RANK finds the nth match"""
    c = _commands()
    c.RPUSH(*[b"k", b"a", b"b", b"a", b"c", b"a"])
    ret = c.LPOS(*[b"k", b"a", b"RANK", b"2"])
    assert ret == protocolBuilder(2)

def test_lpos_check_lpos_with_negative_rank_searches_from_the_tail():
    """Check LPOS with negative RANK searches from the tail"""
    c = _commands()
    c.RPUSH(*[b"k", b"a", b"b", b"a", b"c", b"a"])
    ret = c.LPOS(*[b"k", b"a", b"RANK", b"-1"])
    assert ret == protocolBuilder(4)

def test_lpos_check_lpos_with_negative_rank_2_returns_the_second_from_the_():
    """Check LPOS with negative RANK -2 returns the second from the tail"""
    c = _commands()
    c.RPUSH(*[b"k", b"a", b"b", b"a", b"c", b"a"])
    ret = c.LPOS(*[b"k", b"a", b"RANK", b"-2"])
    assert ret == protocolBuilder(2)

def test_lpos_check_lpos_with_count_returns_every_match():
    """Check LPOS with COUNT returns every match"""
    c = _commands()
    c.RPUSH(*[b"k", b"a", b"b", b"a", b"c", b"a"])
    ret = c.LPOS(*[b"k", b"a", b"COUNT", b"0"])
    assert ret == protocolBuilder([0, 2, 4])

def test_lpos_check_lpos_with_count_limits_the_number_of_matches():
    """Check LPOS with COUNT limits the number of matches"""
    c = _commands()
    c.RPUSH(*[b"k", b"a", b"b", b"a", b"c", b"a"])
    ret = c.LPOS(*[b"k", b"a", b"COUNT", b"2"])
    assert ret == protocolBuilder([0, 2])

def test_lpos_check_lpos_combines_rank_and_count():
    """Check LPOS combines RANK and COUNT"""
    c = _commands()
    c.RPUSH(*[b"k", b"a", b"b", b"a", b"c", b"a"])
    ret = c.LPOS(*[b"k", b"a", b"RANK", b"2", b"COUNT", b"2"])
    assert ret == protocolBuilder([2, 4])

def test_lpos_check_lpos_maxlen_limits_the_scan():
    """Check LPOS MAXLEN limits the scan"""
    c = _commands()
    c.RPUSH(*[b"k", b"a", b"b", b"a", b"c", b"a"])
    ret = c.LPOS(*[b"k", b"c", b"MAXLEN", b"3"])
    assert ret == protocolBuilder(Response.NIL)

def test_lpos_check_lpos_maxlen_still_finds_matches_inside_the_limit():
    """Check LPOS MAXLEN still finds matches inside the limit"""
    c = _commands()
    c.RPUSH(*[b"k", b"a", b"b", b"a", b"c", b"a"])
    ret = c.LPOS(*[b"k", b"c", b"MAXLEN", b"4"])
    assert ret == protocolBuilder(3)

def test_lpos_check_lpos_is_case_insensitive_on_option_names():
    """Check LPOS is case-insensitive on option names"""
    c = _commands()
    c.RPUSH(*[b"k", b"a", b"a"])
    ret = c.LPOS(*[b"k", b"a", b"count", b"1"])
    assert ret == protocolBuilder([0])

def test_lmpop_check_lmpop_on_empty_keys_returns_a_null_array():
    """Check LMPOP on empty keys returns a null array"""
    c = _commands()
    ret = c.LMPOP(*[b"2", b"k1", b"k2", b"LEFT"])
    assert ret == protocolBuilder(Response.NIL_ARRAY)

def test_lmpop_check_lmpop_pops_a_single_element_by_default():
    """Check LMPOP pops a single element by default"""
    c = _commands()
    c.RPUSH(*[b"k", b"a", b"b", b"c"])
    ret = c.LMPOP(*[b"1", b"k", b"LEFT"])
    assert ret == protocolBuilder([b'k', [b'a']])
    assert (list(c.data[b"k"]) == [b"b", b"c"])

def test_lmpop_check_lmpop_with_count_pops_several_elements():
    """Check LMPOP with COUNT pops several elements"""
    c = _commands()
    c.RPUSH(*[b"k", b"a", b"b", b"c"])
    ret = c.LMPOP(*[b"1", b"k", b"LEFT", b"COUNT", b"2"])
    assert ret == protocolBuilder([b'k', [b'a', b'b']])
    assert (list(c.data[b"k"]) == [b"c"])

def test_lmpop_check_lmpop_right_pops_from_the_tail():
    """Check LMPOP RIGHT pops from the tail"""
    c = _commands()
    c.RPUSH(*[b"k", b"a", b"b"])
    ret = c.LMPOP(*[b"1", b"k", b"RIGHT"])
    assert ret == protocolBuilder([b'k', [b'b']])

def test_lmpop_check_lmpop_skips_empty_keys_and_uses_the_first_non_empty_on():
    """Check LMPOP skips empty keys and uses the first non-empty one"""
    c = _commands()
    c.RPUSH(*[b"k3", b"x", b"y"])
    ret = c.LMPOP(*[b"3", b"k1", b"k2", b"k3", b"LEFT"])
    assert ret == protocolBuilder([b'k3', [b'x']])
    assert (list(c.data[b"k3"]) == [b"y"])

def test_lmpop_check_lmpop_pops_the_whole_list_when_count_exceeds_its_lengt():
    """Check LMPOP pops the whole list when COUNT exceeds its length"""
    c = _commands()
    c.RPUSH(*[b"k", b"a", b"b"])
    ret = c.LMPOP(*[b"1", b"k", b"RIGHT", b"COUNT", b"10"])
    assert ret == protocolBuilder([b'k', [b'b', b'a']])
    assert (b"k" not in c.data)

def test_lmpop_check_lmpop_is_case_insensitive_on_the_side_and_options():
    """Check LMPOP is case-insensitive on the side and options"""
    c = _commands()
    c.RPUSH(*[b"k", b"a"])
    ret = c.LMPOP(*[b"1", b"k", b"left", b"count", b"1"])
    assert ret == protocolBuilder([b'k', [b'a']])

def test_lmpop_check_lmpop_replies_with_the_key_of_the_list_it_popped_from():
    """Check LMPOP replies with the key of the list it popped from"""
    c = _commands()
    c.RPUSH(*[b"k1", b"a", b"b"])
    c.RPUSH(*[b"k2", b"x"])
    ret = c.LMPOP(*[b"2", b"k1", b"k2", b"LEFT"])
    assert ret == protocolBuilder([b'k1', [b'a']])
