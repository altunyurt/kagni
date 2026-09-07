"""Hash commands: assert-style spec battery (converted from the
former *_sequence.py table; one function per scenario)."""

from kagni.constants import Response, SimpleString
from kagni.resp import protocolBuilder, protocolParser

from .helpers import _commands


def test_hset_check_hset_return_value_for_nonexisting_key():
    """Check HSET return value for nonexisting key"""
    c = _commands()
    ret = c.HSET(*[b"k", b"f", b"123"])
    assert ret == protocolBuilder(1)
    assert (c.data[b"k"][b"f"] == b"123")

def test_hset_check_hset_return_value_for_existing_key():
    """Check HSET return value for existing key"""
    c = _commands()
    c.HSET(*[b"k", b"f", b"123"])
    ret = c.HSET(*[b"k", b"f", b"foobarz"])
    assert ret == protocolBuilder(0)
    assert (c.data[b"k"][b"f"] == b"foobarz")

def test_hget_check_hget_return_value_for_nonexisting_key():
    """Check HGET return value for nonexisting key"""
    c = _commands()
    ret = c.HGET(*[b"k", b"f"])
    assert ret == protocolBuilder(Response.NIL)

def test_hget_check_hget_return_value_for_nonexisting_field():
    """Check HGET return value for nonexisting field"""
    c = _commands()
    c.HSET(*[b"k", b"another_f", b"123"])
    ret = c.HGET(*[b"k", b"f"])
    assert ret == protocolBuilder(Response.NIL)

def test_hget_check_hget_return_value_for_existing_key():
    """Check HGET return value for existing key"""
    c = _commands()
    c.HSET(*[b"k", b"f", b"foobarz"])
    ret = c.HGET(*[b"k", b"f"])
    assert ret == protocolBuilder(b'foobarz')

def test_hexists_check_hexists_return_value_for_nonexisting_key():
    """Check HEXISTS return value for nonexisting key"""
    c = _commands()
    ret = c.HEXISTS(*[b"k", b"f"])
    assert ret == protocolBuilder(0)

def test_hexists_check_hexists_return_value_for_nonexisting_field():
    """Check HEXISTS return value for nonexisting field"""
    c = _commands()
    c.HSET(*[b"k", b"another_f", b"123"])
    ret = c.HEXISTS(*[b"k", b"f"])
    assert ret == protocolBuilder(0)

def test_hexists_check_hexists_return_value_for_existing_field():
    """Check HEXISTS return value for existing field"""
    c = _commands()
    c.HSET(*[b"k", b"f", b"123"])
    ret = c.HEXISTS(*[b"k", b"f"])
    assert ret == protocolBuilder(1)

def test_hdel_check_hdel_return_value_for_non_existing_key():
    """Check HDEL return value for non existing key"""
    c = _commands()
    ret = c.HDEL(*[b"k", b"f"])
    assert ret == protocolBuilder(0)

def test_hdel_check_hdel_return_value_for_non_existing_fields():
    """Check HDEL return value for non existing fields"""
    c = _commands()
    c.HSET(*[b"k", b"other_key", b"123"])
    ret = c.HDEL(*[b"k", b"f", b"z", b"a"])
    assert ret == protocolBuilder(0)

def test_hdel_check_hdel_return_value_for_some_existing_and_some_not_keys():
    """Check HDEL return value for some existing and some not keys"""
    c = _commands()
    c.HSET(*[b"k", b"f", b"123"])
    c.HSET(*[b"k", b"a", b"123"])
    c.HSET(*[b"k", b"other_key", b"123"])
    c.HSET(*[b"k", b"c", b"123"])
    ret = c.HDEL(*[b"k", b"f", b"z", b"a", b"c"])
    assert ret == protocolBuilder(3)

def test_hgetall_check_hgetall_for_nonexisting_key():
    """Check HGETALL for nonexisting key"""
    c = _commands()
    ret = c.HGETALL(*[b"k"])
    assert ret == protocolBuilder([])

def test_hgetall_check_hgetall_after_its_only_field_was_deleted():
    """Check HGETALL after its only field was deleted"""
    c = _commands()
    c.HSET(*[b"k", b"f", b"123"])
    c.HDEL(*[b"k", b"f"])
    ret = c.HGETALL(*[b"k"])
    assert ret == protocolBuilder([])
    assert (b"k" not in c.data)

def test_hgetall_check_hgetall_return_value_for_existing_key_and_fields():
    """Check HGETALL return value for existing key and fields"""
    c = _commands()
    c.HSET(*[b"k", b"f", b"123"])
    c.HSET(*[b"k", b"a", b"234"])
    c.HSET(*[b"k", b"other_key", b"345"])
    c.HSET(*[b"k", b"c", b"456"])
    ret = c.HGETALL(*[b"k"])
    assert ret == protocolBuilder([b'f', b'123', b'a', b'234', b'other_key', b'345', b'c', b'456'])
