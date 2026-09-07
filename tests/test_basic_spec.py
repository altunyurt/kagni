"""String / generic / admin commands: assert-style spec battery (converted from the
former *_sequence.py table; one function per scenario)."""

from kagni.constants import Response, SimpleString
from kagni.resp import protocolBuilder, protocolParser

from .helpers import _commands


def test_command_check_command_returns_per_command_metadata():
    """Check COMMAND returns per-command metadata"""
    c = _commands()
    ret = c.COMMAND(*[])
    parsed = protocolParser(ret)
    assert (any( entry[:2] == [b"GET", 2] and [b"readonly"] in entry for entry in parsed if isinstance(entry, list) ))

def test_ping_check_ping_return_value():
    """Check PING return value"""
    c = _commands()
    ret = c.PING(*[])
    assert ret == protocolBuilder(Response.PONG)

def test_set_check_set_return_value():
    """Check SET return value"""
    c = _commands()
    ret = c.SET(*[b"a", b"1"])
    assert ret == protocolBuilder(Response.OK)

def test_set_check_re_set_existing_key_return_value():
    """Check re-SET existing key return value"""
    c = _commands()
    c.SET(*[b"b", b"1"])
    ret = c.SET(*[b"b", b"2"])
    assert ret == protocolBuilder(Response.OK)

def test_set_check_set_unicode_byte_string():
    """Check SET unicode byte string"""
    c = _commands()
    ret = c.SET(*[b"d", "fıstıkçışahap".encode("utf-8")])
    assert ret == protocolBuilder(Response.OK)

def test_get_check_get_return_value():
    """Check GET return value"""
    c = _commands()
    c.SET(*[b"d", b"10"])
    ret = c.GET(*[b"d"])
    assert ret == protocolBuilder(b'10')

def test_get_check_get_nonexisting_key_return_value():
    """Check GET nonexisting key return value"""
    c = _commands()
    ret = c.GET(*[b"d"])
    assert ret == protocolBuilder(Response.NIL)

def test_get_check_get_return_value_for_unicode_encoded_string():
    """Check GET return value for unicode encoded string"""
    c = _commands()
    c.SET(*[b"d", "fıstıkçışahap".encode("utf-8")])
    ret = c.GET(*[b"d"])
    assert ret == protocolBuilder(b'f\xc4\xb1st\xc4\xb1k\xc3\xa7\xc4\xb1\xc5\x9fahap')

def test_getset_check_getset_return_value():
    """Check GETSET return value"""
    c = _commands()
    c.SET(*[b"d", b"10"])
    ret = c.GETSET(*[b"d", b"20"])
    assert ret == protocolBuilder(b'10')
    assert (c.data.get(b"d") == b"20")

def test_getset_check_getset_nonexisting_key_return_value():
    """Check GETSET nonexisting key return value"""
    c = _commands()
    ret = c.GETSET(*[b"d", b"10"])
    assert ret == protocolBuilder(Response.NIL)
    assert (c.data.get(b"d") == b"10")

def test_getset_check_getset_return_value_for_unicode_encoded_string():
    """Check GETSET return value for unicode encoded string"""
    c = _commands()
    c.SET(*[b"d", "fıstıkçışahap".encode("utf-8")])
    ret = c.GETSET(*[b"d", b"foobarz"])
    assert ret == protocolBuilder(b'f\xc4\xb1st\xc4\xb1k\xc3\xa7\xc4\xb1\xc5\x9fahap')
    assert (c.data.get(b"d") == b"foobarz")

def test_mset_check_mset_return_value():
    """Check MSET return value"""
    c = _commands()
    ret = c.MSET(*[
                b"e",
                b"1",
                b"f",
                b"3424gshm",
                b"g",
                "fıstıkçışahap".encode("utf-8"),
            ])
    assert ret == protocolBuilder(Response.OK)

def test_mget_mget_scenario():
    """MGET scenario"""
    c = _commands()
    c.SET(*[b"a", b"1"])
    c.SET(*[b"b", b"2"])
    c.SET(*[b"c", b"3"])
    c.SET(*[b"d", b"4"])
    ret = c.MGET(*[b"a", b"b", b"c"])
    assert ret == protocolBuilder([b'1', b'2', b'3'])

def test_del_check_del_return_value_on_existing_keys():
    """Check DEL return value on existing keys"""
    c = _commands()
    c.SET(*[b"e", b"1"])
    c.SET(*[b"f", b"2"])
    c.SET(*[b"g", b"3"])
    c.SET(*[b"d", b"4"])
    ret = c.DEL(*[b"e", b"f", b"g"])
    assert ret == protocolBuilder(3)

def test_append_check_append_with_non_existing_key():
    """Check APPEND with non existing key"""
    c = _commands()
    ret = c.APPEND(*[b"k", b"world"])
    assert ret == protocolBuilder(5)

def test_append_check_append_with_existing_key():
    """Check APPEND with  existing key"""
    c = _commands()
    c.SET(*[b"k", b"Hello"])
    ret = c.APPEND(*[b"k", b" world"])
    assert ret == protocolBuilder(11)

def test_del_check_del_return_value_on_non_existing_keys():
    """Check DEL return value on non existing keys"""
    c = _commands()
    ret = c.DEL(*[b"e", b"f", b"g", b"nonexistent"])
    assert ret == protocolBuilder(0)

def test_expire_check_expire_retval_on_existing_key():
    """Check expire retval on existing key"""
    c = _commands()
    c.SET(*[b"e", b"1"])
    ret = c.EXPIRE(*[b"e", b"10"])
    assert ret == protocolBuilder(1)

def test_expire_check_expire_retval_on_existing_key_2():
    """Check expire retval on existing key"""
    c = _commands()
    ret = c.EXPIRE(*[b"non-existent", b"10"])
    assert ret == protocolBuilder(0)

def test_ttl_check_ttl_on_key():
    """Check ttl on key"""
    c = _commands()
    c.SET(*[b"e", b"1"])
    c.EXPIRE(*[b"e", b"10"])
    ret = c.TTL(*[b"e"])
    assert ret == protocolBuilder(10)

def test_ttl_check_ttl_on_key_with_no_expiration():
    """Check ttl on key with no expiration"""
    c = _commands()
    c.SET(*[b"e", b"1"])
    ret = c.TTL(*[b"e"])
    assert ret == protocolBuilder(-1)

def test_ttl_check_ttl_on_expired_key():
    """Check TTL on expired key"""
    c = _commands()
    c.SET(*[b"e", b"1"])
    c.EXPIRE(*[b"e", b"-10"])
    ret = c.TTL(*[b"e"])
    assert ret == protocolBuilder(-2)

def test_ttl_check_ttl_on_nonexisting_key():
    """Check TTL on nonexisting key"""
    c = _commands()
    ret = c.TTL(*[b"nonexistent"])
    assert ret == protocolBuilder(-2)

def test_keys_check_keys_with_glob_pattern_return_value():
    """Check KEYS with glob * pattern return value"""
    c = _commands()
    c.MSET(*[b"a", b"1", b"b", b"1", b"c", b"1", b"d", b"1", b"e", b"1"])
    ret = c.KEYS(*[b"*"])
    assert ret == protocolBuilder([b'a', b'b', b'c', b'd', b'e'])

def test_keys_check_keys_with_glob_pattern_return_value_2():
    """Check KEYS with glob pattern return value"""
    c = _commands()
    c.MSET(*[b"a", b"1", b"b", b"1", b"c", b"1", b"d", b"1", b"e", b"1"])
    ret = c.KEYS(*[b"*"])
    assert ret == protocolBuilder([b'a', b'b', b'c', b'd', b'e'])

def test_keys_check_keys_with_glob_pattern_return_value_3():
    """Check KEYS with glob * pattern return value"""
    c = _commands()
    c.MSET(*[b"a", b"1", b"b", b"1", b"c", b"1", b"d", b"1", b"e", b"1"])
    ret = c.KEYS(*[b"[ae]*"])
    assert ret == protocolBuilder([b'a', b'e'])

def test_keys_check_keys_with_glob_non_matching_pattern_return_value():
    """Check KEYS with glob non-matching pattern return value"""
    c = _commands()
    c.MSET(*[b"a", b"1", b"b", b"1", b"c", b"1", b"d", b"1", b"e", b"1"])
    ret = c.KEYS(*[b"[gf]*"])
    assert ret == protocolBuilder([])

def test_incr_check_incr_return_value():
    """Check INCR return value """
    c = _commands()
    c.SET(*[b"b", b"1"])
    ret = c.INCR(*[b"b"])
    assert ret == protocolBuilder(2)

def test_incr_check_incr_return_value_on_nonexisting_key():
    """Check INCR return value on nonexisting key"""
    c = _commands()
    ret = c.INCR(*[b"c"])
    assert ret == protocolBuilder(1)

def test_incrby_check_incrby_return_value():
    """Check INCRBY return value """
    c = _commands()
    c.SET(*[b"b", b"75"])
    ret = c.INCRBY(*[b"b", b"18"])
    assert ret == protocolBuilder(93)

def test_incrby_check_incrby_return_value_on_nonexisting_key():
    """Check INCRBY return value on nonexisting key"""
    c = _commands()
    ret = c.INCRBY(*[b"c", b"23"])
    assert ret == protocolBuilder(23)

def test_decr_check_decr_return_value():
    """Check DECR return value """
    c = _commands()
    c.SET(*[b"b", b"1"])
    ret = c.DECR(*[b"b"])
    assert ret == protocolBuilder(0)

def test_decr_check_decr_return_value_on_nonexisting_key():
    """Check DECR return value on nonexisting key"""
    c = _commands()
    ret = c.DECR(*[b"c"])
    assert ret == protocolBuilder(-1)

def test_decrby_check_decrby_return_value():
    """Check DECRBY return value """
    c = _commands()
    c.SET(*[b"b", b"75"])
    ret = c.DECRBY(*[b"b", b"18"])
    assert ret == protocolBuilder(57)

def test_decrby_check_decrby_return_value_on_nonexisting_key():
    """Check DECRBY return value on nonexisting key"""
    c = _commands()
    ret = c.DECRBY(*[b"c", b"23"])
    assert ret == protocolBuilder(-23)

def test_getrange_check_getrange_return_value():
    """Check GETRANGE return value """
    c = _commands()
    c.SET(*[b"b", b"hello world"])
    ret = c.GETRANGE(*[b"b", b"4", b"10"])
    assert ret == protocolBuilder(b'o world')

def test_getrange_check_getrange_return_value_on_nonexisting_key():
    """Check GETRANGE return value on nonexisting key """
    c = _commands()
    ret = c.GETRANGE(*[b"b", b"4", b"10"])
    assert ret == protocolBuilder(b'')

def test_setrange_check_setrange_with_nonexisting_key():
    """Check SETRANGE with nonexisting key"""
    c = _commands()
    ret = c.SETRANGE(*[b"b", b"10", b"Hello"])
    assert ret == protocolBuilder(15)
    assert (c.data.get(b"b") == b"\x00" * 10 + b"Hello")

def test_setrange_check_setrange_return_value_on_existing_key_offset_inside():
    """Check SETRANGE return value on existing key offset inside"""
    c = _commands()
    c.SET(*[b"b", b"Hello World"])
    ret = c.SETRANGE(*[b"b", b"5", b"deneme"])
    assert ret == protocolBuilder(11)
    assert (c.data.get(b"b") == b"Hellodeneme")

def test_setrange_check_setrange_return_value_on_existing_key_offset_outside():
    """Check SETRANGE return value on existing key offset outside"""
    c = _commands()
    c.SET(*[b"b", b"Hello World"])
    ret = c.SETRANGE(*[b"b", b"50", b"deneme"])
    assert ret == protocolBuilder(56)
    assert (c.data.get(b"b") == b"Hello World" + b"\x00" * 39 + b"deneme")

def test_flushdb_check_flushdb_works():
    """Check FLUSHDB works"""
    c = _commands()
    c.SETBIT(*[b"b", b"0", b"1"])
    c.SETBIT(*[b"b", b"1", b"1"])
    c.SETBIT(*[b"b", b"2", b"1"])
    c.SETBIT(*[b"b", b"4", b"1"])
    ret = c.FLUSHDB(*[])
    assert ret == protocolBuilder(Response.OK)
    assert (len(c.data) == 0)

def test_flushall_check_flushall_works():
    """Check FLUSHALL works"""
    c = _commands()
    c.SETBIT(*[b"b", b"0", b"1"])
    c.SETBIT(*[b"b", b"1", b"1"])
    c.SETBIT(*[b"b", b"2", b"1"])
    c.SETBIT(*[b"b", b"4", b"1"])
    ret = c.FLUSHALL(*[])
    assert ret == protocolBuilder(Response.OK)
    assert (len(c.data) == 0)

def test_type_check_type_on_a_missing_key():
    """Check TYPE on a missing key"""
    c = _commands()
    ret = c.TYPE(*[b"k"])
    assert ret == protocolBuilder(SimpleString('none'))

def test_type_check_type_on_a_string_key():
    """Check TYPE on a string key"""
    c = _commands()
    c.SET(*[b"k", b"v"])
    ret = c.TYPE(*[b"k"])
    assert ret == protocolBuilder(SimpleString('string'))

def test_type_check_type_on_a_hash_key():
    """Check TYPE on a hash key"""
    c = _commands()
    c.HSET(*[b"k", b"f", b"v"])
    ret = c.TYPE(*[b"k"])
    assert ret == protocolBuilder(SimpleString('hash'))

def test_type_check_type_on_a_set_key():
    """Check TYPE on a set key"""
    c = _commands()
    c.SADD(*[b"k", b"m"])
    ret = c.TYPE(*[b"k"])
    assert ret == protocolBuilder(SimpleString('set'))

def test_set_check_set_with_ex_sets_a_ttl():
    """Check SET with EX sets a TTL"""
    c = _commands()
    ret = c.SET(*[b"k", b"v", b"EX", b"100"])
    assert ret == protocolBuilder(Response.OK)
    assert (c.data.ttl(b"k") > 0)

def test_set_check_set_with_keepttl_keeps_the_ttl():
    """Check SET with KEEPTTL keeps the TTL"""
    c = _commands()
    c.SET(*[b"k", b"v", b"EX", b"100"])
    ret = c.SET(*[b"k", b"v2", b"KEEPTTL"])
    assert ret == protocolBuilder(Response.OK)
    assert (c.data.ttl(b"k") > 0)

def test_set_check_plain_set_clears_an_existing_ttl():
    """Check plain SET clears an existing TTL"""
    c = _commands()
    c.SET(*[b"k", b"v", b"EX", b"100"])
    ret = c.SET(*[b"k", b"v2"])
    assert ret == protocolBuilder(Response.OK)
    assert (c.data.ttl(b"k") == -1)

def test_set_check_set_nx_on_a_missing_key():
    """Check SET NX on a missing key"""
    c = _commands()
    ret = c.SET(*[b"k", b"v", b"NX"])
    assert ret == protocolBuilder(Response.OK)
    assert (c.data.get(b"k") == b"v")

def test_set_check_set_nx_on_an_existing_key_returns_nil():
    """Check SET NX on an existing key returns nil"""
    c = _commands()
    c.SET(*[b"k", b"v", b"NX"])
    ret = c.SET(*[b"k", b"v2", b"NX"])
    assert ret == protocolBuilder(Response.NIL)
    assert (c.data.get(b"k") == b"v")

def test_set_check_set_xx_on_an_existing_key():
    """Check SET XX on an existing key"""
    c = _commands()
    c.SET(*[b"k", b"v", b"NX"])
    ret = c.SET(*[b"k", b"v2", b"XX"])
    assert ret == protocolBuilder(Response.OK)
    assert (c.data.get(b"k") == b"v2")

def test_set_check_set_xx_on_a_missing_key_returns_nil():
    """Check SET XX on a missing key returns nil"""
    c = _commands()
    ret = c.SET(*[b"k", b"v", b"XX"])
    assert ret == protocolBuilder(Response.NIL)
    assert (b"k" not in c.data)

def test_set_check_set_with_get_returns_the_old_value():
    """Check SET with GET returns the old value"""
    c = _commands()
    c.SET(*[b"k", b"v", b"NX"])
    ret = c.SET(*[b"k", b"v2", b"GET"])
    assert ret == protocolBuilder(b'v')
    assert (c.data.get(b"k") == b"v2")

def test_set_check_set_with_get_on_a_missing_key_returns_nil_and_sets():
    """Check SET with GET on a missing key returns nil and sets"""
    c = _commands()
    ret = c.SET(*[b"k", b"v", b"GET"])
    assert ret == protocolBuilder(Response.NIL)
    assert (c.data.get(b"k") == b"v")

def test_set_check_set_nx_get_on_an_existing_key_returns_it_unchanged():
    """Check SET NX GET on an existing key returns it unchanged"""
    c = _commands()
    c.SET(*[b"k", b"v", b"NX"])
    ret = c.SET(*[b"k", b"blocked", b"NX", b"GET"])
    assert ret == protocolBuilder(b'v')
    assert (c.data.get(b"k") == b"v")

def test_setnx_check_setnx_on_a_missing_key():
    """Check SETNX on a missing key"""
    c = _commands()
    ret = c.SETNX(*[b"k", b"v"])
    assert ret == protocolBuilder(1)
    assert (c.data.get(b"k") == b"v")

def test_setnx_check_setnx_on_an_existing_key():
    """Check SETNX on an existing key"""
    c = _commands()
    c.SETNX(*[b"k", b"v"])
    ret = c.SETNX(*[b"k", b"v2"])
    assert ret == protocolBuilder(0)
    assert (c.data.get(b"k") == b"v")

def test_setex_check_setex_sets_a_value_with_a_ttl():
    """Check SETEX sets a value with a TTL"""
    c = _commands()
    ret = c.SETEX(*[b"k", b"100", b"v"])
    assert ret == protocolBuilder(Response.OK)
    assert (c.data.get(b"k") == b"v" and c.data.ttl(b"k") > 0)

def test_psetex_check_psetex_sets_a_value_with_a_ttl():
    """Check PSETEX sets a value with a TTL"""
    c = _commands()
    ret = c.PSETEX(*[b"k", b"100000", b"v"])
    assert ret == protocolBuilder(Response.OK)
    assert (c.data.get(b"k") == b"v" and c.data.ttl(b"k") > 0)

def test_getdel_check_getdel_returns_the_value_and_removes_the_key():
    """Check GETDEL returns the value and removes the key"""
    c = _commands()
    c.SET(*[b"k", b"v"])
    ret = c.GETDEL(*[b"k"])
    assert ret == protocolBuilder(b'v')
    assert (b"k" not in c.data)

def test_getdel_check_getdel_on_a_missing_key():
    """Check GETDEL on a missing key"""
    c = _commands()
    ret = c.GETDEL(*[b"k"])
    assert ret == protocolBuilder(Response.NIL)

def test_getex_check_getex_returns_the_value():
    """Check GETEX returns the value"""
    c = _commands()
    c.SET(*[b"k", b"v"])
    ret = c.GETEX(*[b"k"])
    assert ret == protocolBuilder(b'v')

def test_getex_check_getex_on_a_missing_key():
    """Check GETEX on a missing key"""
    c = _commands()
    ret = c.GETEX(*[b"k"])
    assert ret == protocolBuilder(Response.NIL)

def test_getex_check_getex_with_ex_sets_a_ttl():
    """Check GETEX with EX sets a TTL"""
    c = _commands()
    c.SET(*[b"k", b"v"])
    ret = c.GETEX(*[b"k", b"EX", b"100"])
    assert ret == protocolBuilder(b'v')
    assert (c.data.ttl(b"k") > 0)

def test_getex_check_getex_with_persist_clears_the_ttl():
    """Check GETEX with PERSIST clears the TTL"""
    c = _commands()
    c.SET(*[b"k", b"v", b"EX", b"100"])
    ret = c.GETEX(*[b"k", b"PERSIST"])
    assert ret == protocolBuilder(b'v')
    assert (c.data.ttl(b"k") == -1)

def test_msetnx_check_msetnx_sets_all_keys_when_none_exist():
    """Check MSETNX sets all keys when none exist"""
    c = _commands()
    ret = c.MSETNX(*[b"a", b"1", b"b", b"2"])
    assert ret == protocolBuilder(1)
    assert (c.data.get(b"a") == b"1" and c.data.get(b"b") == b"2")

def test_msetnx_check_msetnx_sets_nothing_when_a_key_exists():
    """Check MSETNX sets nothing when a key exists"""
    c = _commands()
    c.MSETNX(*[b"a", b"1", b"b", b"2"])
    ret = c.MSETNX(*[b"a", b"9", b"c", b"3"])
    assert ret == protocolBuilder(0)
    assert (c.data.get(b"a") == b"1" and c.data.get(b"c") is None)

def test_exists_check_exists_counts_existing_keys():
    """Check EXISTS counts existing keys"""
    c = _commands()
    c.SET(*[b"a", b"1"])
    c.SET(*[b"b", b"2"])
    ret = c.EXISTS(*[b"a", b"b", b"nope"])
    assert ret == protocolBuilder(2)

def test_exists_check_exists_on_missing_keys():
    """Check EXISTS on missing keys"""
    c = _commands()
    ret = c.EXISTS(*[b"nope"])
    assert ret == protocolBuilder(0)

def test_touch_check_touch_counts_existing_keys():
    """Check TOUCH counts existing keys"""
    c = _commands()
    c.SET(*[b"a", b"1"])
    ret = c.TOUCH(*[b"a", b"nope"])
    assert ret == protocolBuilder(1)

def test_dbsize_check_dbsize():
    """Check DBSIZE"""
    c = _commands()
    c.SET(*[b"a", b"1"])
    c.SET(*[b"b", b"2"])
    ret = c.DBSIZE(*[])
    assert ret == protocolBuilder(2)

def test_incrbyfloat_check_incrbyfloat_on_a_missing_key_starts_from_zero():
    """Check INCRBYFLOAT on a missing key starts from zero"""
    c = _commands()
    ret = c.INCRBYFLOAT(*[b"f", b"10.5"])
    assert ret == protocolBuilder(b'10.5')
    assert (c.data.get(b"f") == b"10.5")

def test_incrbyfloat_check_incrbyfloat_subtracts_back_to_an_integer():
    """Check INCRBYFLOAT subtracts back to an integer"""
    c = _commands()
    c.INCRBYFLOAT(*[b"f", b"10.5"])
    ret = c.INCRBYFLOAT(*[b"f", b"-10.5"])
    assert ret == protocolBuilder(b'0')

def test_incrbyfloat_check_incrbyfloat_float_precision():
    """Check INCRBYFLOAT float precision"""
    c = _commands()
    c.SET(*[b"f", b"0.1"])
    ret = c.INCRBYFLOAT(*[b"f", b"0.2"])
    assert ret == protocolBuilder(b'0.30000000000000004')

def test_incrbyfloat_check_incrbyfloat_on_an_integer_string():
    """Check INCRBYFLOAT on an integer string"""
    c = _commands()
    c.SET(*[b"f", b"10"])
    ret = c.INCRBYFLOAT(*[b"f", b"0.5"])
    assert ret == protocolBuilder(b'10.5')

def test_scan_check_scan_returns_the_whole_snapshot_in_one_step():
    """Check SCAN returns the whole snapshot in one step"""
    c = _commands()
    c.SET(*[b"a", b"1"])
    c.SET(*[b"b", b"2"])
    ret = c.SCAN(*[b"0"])
    assert ret == protocolBuilder([b'0', [b'a', b'b']])

def test_scan_check_scan_on_an_empty_keyspace():
    """Check SCAN on an empty keyspace"""
    c = _commands()
    ret = c.SCAN(*[b"0"])
    assert ret == protocolBuilder([b'0', []])

def test_scan_check_scan_with_match():
    """Check SCAN with MATCH"""
    c = _commands()
    c.SET(*[b"a1", b"1"])
    c.SET(*[b"b1", b"2"])
    ret = c.SCAN(*[b"0", b"MATCH", b"a*"])
    assert ret == protocolBuilder([b'0', [b'a1']])

def test_scan_check_scan_with_type_filter():
    """Check SCAN with TYPE filter"""
    c = _commands()
    c.SET(*[b"str", b"1"])
    c.HSET(*[b"hsh", b"f", b"v"])
    ret = c.SCAN(*[b"0", b"TYPE", b"hash"])
    assert ret == protocolBuilder([b'0', [b'hsh']])

def test_client_check_client_setinfo_is_accepted():
    """Check CLIENT SETINFO is accepted"""
    c = _commands()
    ret = c.CLIENT(*[b"SETINFO", b"lib-name", b"redis-py"])
    assert ret == protocolBuilder(Response.OK)

def test_client_check_client_setname_is_accepted():
    """Check CLIENT SETNAME is accepted"""
    c = _commands()
    ret = c.CLIENT(*[b"SETNAME", b"conn-1"])
    assert ret == protocolBuilder(Response.OK)

def test_client_check_client_getname_returns_an_empty_bulk():
    """Check CLIENT GETNAME returns an empty bulk"""
    c = _commands()
    ret = c.CLIENT(*[b"GETNAME"])
    assert ret == protocolBuilder(b'')

def test_client_check_client_id():
    """Check CLIENT ID"""
    c = _commands()
    ret = c.CLIENT(*[b"ID"])
    assert ret == protocolBuilder(1)
