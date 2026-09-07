"""Set commands: assert-style spec battery (converted from the
former *_sequence.py table; one function per scenario)."""

from kagni.constants import Response, SimpleString
from kagni.resp import protocolBuilder, protocolParser

from .helpers import _commands


def test_sadd_check_sadd_return_value_for_nonexisting_key():
    """Check SADD return value for nonexisting key"""
    c = _commands()
    ret = c.SADD(*[b"k", b"1", b"a", b"3", b"7"])
    assert ret == protocolBuilder(4)

def test_sadd_check_sadd_return_value_for_existing_key():
    """Check SADD return value for existing key"""
    c = _commands()
    c.SADD(*[b"k", b"1", b"a", b"3", b"7"])
    ret = c.SADD(*[b"k", b"2", b"b", b"5", b"6"])
    assert ret == protocolBuilder(4)

def test_sadd_check_sadd_return_value_for_existing_key_and_conflicting_val():
    """Check SADD return value for existing key and conflicting values"""
    c = _commands()
    c.SADD(*[b"k", b"1", b"a", b"3", b"7"])
    ret = c.SADD(*[b"k", b"1", b"b", b"3", b"6"])
    assert ret == protocolBuilder(2)

def test_scard_check_scard_return_value_for_nonexisting_key():
    """Check SCARD return value for nonexisting key"""
    c = _commands()
    ret = c.SCARD(*[b"k"])
    assert ret == protocolBuilder(0)

def test_scard_check_scard_return_value_for_existing_key():
    """Check SCARD return value for existing key"""
    c = _commands()
    c.SADD(*[b"k", b"1", b"a", b"3", b"7"])
    ret = c.SCARD(*[b"k"])
    assert ret == protocolBuilder(4)

def test_smembers_check_smembers_return_value_for_existing_key():
    """Check SMEMBERS return value for existing key"""
    c = _commands()
    ret = c.SMEMBERS(*[b"k"])
    parsed = protocolParser(ret)
    assert sorted(parsed) == sorted([])

def test_smembers_check_smembers_return_value_for_existing_key_2():
    """Check SMEMBERS return value for existing key"""
    c = _commands()
    c.SADD(*[b"k", b"1", b"a", b"3", b"7"])
    ret = c.SMEMBERS(*[b"k"])
    parsed = protocolParser(ret)
    assert sorted(parsed) == sorted([b'3', b'a', b'1', b'7'])

def test_srem_check_srem_return_value_for_existing_key():
    """Check SREM return value for existing key"""
    c = _commands()
    ret = c.SREM(*[b"k", b"a"])
    assert ret == protocolBuilder(0)

def test_srem_check_srem_return_value_for_existing_key_2():
    """Check SREM return value for existing key"""
    c = _commands()
    c.SADD(*[b"k", b"1", b"2", b"3", b"4", b"5", b"6", b"7", b"8", b"9"])
    ret = c.SREM(*[b"k", b"1", b"2", b"hm", b"3", b"rn", b"78"])
    assert ret == protocolBuilder(3)

def test_sdiff_check_sdiff_value_for_non_existing_key():
    """Check SDIFF value for non existing key"""
    c = _commands()
    ret = c.SDIFF(*[b"k", b"a", b"b"])
    parsed = protocolParser(ret)
    assert sorted(parsed) == sorted([])

def test_sdiff_check_sdiff_value_for_existing_key_with_non_existing_diff_ke():
    """Check SDIFF value for existing key with non existing diff keys """
    c = _commands()
    c.SADD(*[b"k", b"1", b"2", b"3", b"4"])
    ret = c.SDIFF(*[b"k", b"a", b"b"])
    parsed = protocolParser(ret)
    assert sorted(parsed) == sorted([b'3', b'2', b'1', b'4'])

def test_sdiff_check_sdiff_return_value_for_existing_key():
    """Check SDIFF return value for existing key"""
    c = _commands()
    c.SADD(*[b"k", b"1", b"2", b"3", b"4", b"5", b"6", b"7", b"8", b"9"])
    c.SADD(*[b"a", b"4", b"5", b"6", b"7", b"8", b"9"])
    c.SADD(*[b"b", b"10", b"20", b"30", b"40"])
    ret = c.SDIFF(*[b"k", b"a", b"b"])
    parsed = protocolParser(ret)
    assert sorted(parsed) == sorted([b'3', b'2', b'1'])

def test_sdiffstore_check_sdiffstore_value_for_non_existing_key():
    """Check SDIFFSTORE value for non existing key"""
    c = _commands()
    ret = c.SDIFFSTORE(*[b"k", b"a", b"b", b"c"])
    assert ret == protocolBuilder(0)

def test_sdiffstore_check_sdiffstore_value_for_existing_key_with_non_existing_di():
    """Check SDIFFSTORE value for existing key with non existing diff keys """
    c = _commands()
    c.SADD(*[b"k", b"1", b"2", b"3", b"4"])
    ret = c.SDIFFSTORE(*[b"k", b"a", b"b", b"c"])
    assert ret == protocolBuilder(0)

def test_sdiffstore_check_sdiffstore_value_for_existing_key_with_some_existing_d():
    """Check SDIFFSTORE value for existing key with some existing diff keys """
    c = _commands()
    c.SADD(*[b"k", b"1", b"3", b"4"])
    c.SADD(*[b"a", b"10", b"20", b"30", b"40", b"50"])
    ret = c.SDIFFSTORE(*[b"k", b"a", b"b", b"c"])
    assert ret == protocolBuilder(5)

def test_sdiffstore_check_sdiffstore_return_value_for_existing_key():
    """Check SDIFFSTORE return value for existing key"""
    c = _commands()
    c.SADD(*[b"a", b"1", b"2", b"3", b"4", b"5", b"6", b"7", b"8", b"9"])
    c.SADD(*[b"b", b"4", b"5", b"6", b"7", b"8", b"9"])
    c.SADD(*[b"c", b"2", b"10", b"20", b"30", b"40"])
    ret = c.SDIFFSTORE(*[b"k", b"a", b"b", b"c"])
    assert ret == protocolBuilder(2)

def test_sinter_check_sinter_value_for_non_existing_key():
    """Check SINTER value for non existing key"""
    c = _commands()
    ret = c.SINTER(*[b"k", b"a", b"b"])
    parsed = protocolParser(ret)
    assert sorted(parsed) == sorted([])

def test_sinter_check_sinter_value_for_existing_key_with_non_existing_inter_():
    """Check SINTER value for existing key with non existing inter keys """
    c = _commands()
    c.SADD(*[b"k", b"1", b"2", b"3", b"4"])
    ret = c.SINTER(*[b"k", b"a", b"b"])
    parsed = protocolParser(ret)
    assert sorted(parsed) == sorted([])

def test_sinter_check_sinter_return_value_for_existing_key():
    """Check SINTER return value for existing key"""
    c = _commands()
    c.SADD(*[b"k", b"1", b"2", b"3", b"4", b"5", b"6", b"7", b"8", b"9"])
    c.SADD(*[b"a", b"4", b"5", b"6", b"7", b"8", b"9"])
    c.SADD(*[b"b", b"10", b"20", b"30", b"40", b"5", b"6"])
    ret = c.SINTER(*[b"k", b"a", b"b"])
    parsed = protocolParser(ret)
    assert sorted(parsed) == sorted([b'5', b'6'])

def test_sinterstore_check_sinterstore_value_for_non_existing_key():
    """Check SINTERSTORE value for non existing key"""
    c = _commands()
    ret = c.SINTERSTORE(*[b"k", b"a", b"b", b"c"])
    assert ret == protocolBuilder(0)

def test_sinterstore_check_sinterstore_value_for_existing_key_with_non_existing_d():
    """Check SINTERSTORE value for existing key with non existing diff keys """
    c = _commands()
    c.SADD(*[b"k", b"1", b"2", b"3", b"4"])
    ret = c.SINTERSTORE(*[b"k", b"a", b"b", b"c"])
    assert ret == protocolBuilder(0)

def test_sinterstore_check_sinterstore_value_for_existing_key_with_some_existing_():
    """Check SINTERSTORE value for existing key with some existing diff keys """
    c = _commands()
    c.SADD(*[b"k", b"1", b"3", b"4", b"89"])
    c.SADD(*[b"a", b"10", b"20", b"30", b"40", b"50"])
    c.SADD(*[b"b", b"10", b"40", b"50"])
    ret = c.SINTERSTORE(*[b"k", b"a", b"b"])
    assert ret == protocolBuilder(3)

def test_sismember_check_sismember_with_nonexisting_key():
    """Check SISMEMBER with nonexisting key"""
    c = _commands()
    ret = c.SISMEMBER(*[b"k", b"a"])
    assert ret == protocolBuilder(0)

def test_sismember_check_sismember_with_nonmember_value():
    """Check SISMEMBER with nonmember value"""
    c = _commands()
    c.SADD(*[b"k", b"1", b"3", b"4", b"89"])
    ret = c.SISMEMBER(*[b"k", b"a"])
    assert ret == protocolBuilder(0)

def test_sismember_check_sismember_with_existing_value():
    """Check SISMEMBER with existing value"""
    c = _commands()
    c.SADD(*[b"k", b"1", b"3", b"a", b"4", b"89"])
    ret = c.SISMEMBER(*[b"k", b"a"])
    assert ret == protocolBuilder(1)

def test_smove_check_smove_with_nonexisting_key():
    """Check SMOVE with nonexisting key"""
    c = _commands()
    ret = c.SMOVE(*[b"s", b"t", b"val"])
    assert ret == protocolBuilder(0)

def test_smove_check_smove_with_existing_key_nonmember_value():
    """Check SMOVE with existing key nonmember value"""
    c = _commands()
    c.SADD(*[b"s", b"notval"])
    ret = c.SMOVE(*[b"s", b"t", b"val"])
    assert ret == protocolBuilder(0)

def test_smove_check_smove_with_member_value_non_existing_target():
    """Check SMOVE with member value non existing target"""
    c = _commands()
    c.SADD(*[b"s", b"val"])
    ret = c.SMOVE(*[b"s", b"t", b"val"])
    assert ret == protocolBuilder(1)
    assert (b"s" not in c.data and b"val" in c.data[b"t"])

def test_smove_check_smove_with_member_value_existing_target_having_the_sam():
    """Check SMOVE with member value  existing target having the same value"""
    c = _commands()
    c.SADD(*[b"s", b"val"])
    c.SADD(*[b"t", b"val"])
    ret = c.SMOVE(*[b"s", b"t", b"val"])
    assert ret == protocolBuilder(1)
    assert (b"s" not in c.data and b"val" in c.data[b"t"])

def test_smove_check_smove_with_member_value_existing_target_not_having_the():
    """Check SMOVE with member value  existing target not having the value"""
    c = _commands()
    c.SADD(*[b"s", b"val"])
    c.SADD(*[b"t", b"notval"])
    ret = c.SMOVE(*[b"s", b"t", b"val"])
    assert ret == protocolBuilder(1)
    assert (b"s" not in c.data and b"val" in c.data[b"t"])

def test_spop_check_spop_with_nonexisting_key():
    """Check SPOP with nonexisting key"""
    c = _commands()
    ret = c.SPOP(*[b"k"])
    assert ret == protocolBuilder(Response.NIL)

def test_spop_check_spop_with_only_existing_key():
    """Check SPOP with only existing key"""
    c = _commands()
    c.SADD(*[b"k", b"1"])
    ret = c.SPOP(*[b"k"])
    assert ret == protocolBuilder(b'1')

def test_spop_check_spop_with_a_sample_size_less_than_set_size():
    """Check SPOP with a sample size less than set size"""
    c = _commands()
    c.SADD(*[b"k", b"1", b"2", b"3", b"4", b"5"])
    ret = c.SPOP(*[b"k", b"3"])
    parsed = protocolParser(ret)
    assert (set([b"1", b"2", b"3", b"4", b"5"]).issuperset( set(parsed) ))

def test_spop_check_spop_with_count_bigger_than_set_size():
    """Check SPOP with count bigger than set size"""
    c = _commands()
    c.SADD(*[b"k", b"1", b"2"])
    ret = c.SPOP(*[b"k", b"3"])
    parsed = protocolParser(ret)
    assert sorted(parsed) == sorted([b'2', b'1'])

def test_srandmember_check_srandmember_with_nonexisting_key():
    """Check SRANDMEMBER with nonexisting key"""
    c = _commands()
    ret = c.SRANDMEMBER(*[b"k"])
    assert ret == protocolBuilder(Response.NIL)

def test_srandmember_check_srandmember_with_only_existing_key():
    """Check SRANDMEMBER with only existing key"""
    c = _commands()
    c.SADD(*[b"k", b"1"])
    ret = c.SRANDMEMBER(*[b"k"])
    assert ret == protocolBuilder(b'1')

def test_srandmember_check_srandmember_with_a_sample_size_less_than_set_size():
    """Check SRANDMEMBER with a sample size less than set size"""
    c = _commands()
    c.SADD(*[b"k", b"1", b"2", b"3", b"4", b"5"])
    ret = c.SRANDMEMBER(*[b"k", b"3"])
    parsed = protocolParser(ret)
    assert (c.data[b"k"].issuperset(set(parsed)))

def test_srandmember_check_srandmember_with_count_bigger_than_set_size():
    """Check SRANDMEMBER with count bigger than set size"""
    c = _commands()
    c.SADD(*[b"k", b"1", b"2"])
    ret = c.SRANDMEMBER(*[b"k", b"3"])
    parsed = protocolParser(ret)
    assert sorted(parsed) == sorted([b'2', b'1'])
