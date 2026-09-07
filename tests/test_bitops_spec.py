"""Bitmap (SETBIT-family) commands: per-command spec battery, one pytest case per scenario."""

from kagni.resp import protocolBuilder

from .helpers import _commands

def test_setbit_check_setbit_return_value_on_non_existing_key():
    """Check SETBIT return value on non existing key"""
    c = _commands()
    ret = c.SETBIT(*[b"b", b"1", b"1"])
    assert ret == protocolBuilder(0)

def test_setbit_check_setbit_return_value_on_existing_key():
    """Check SETBIT return value on existing key"""
    c = _commands()
    c.SETBIT(*[b"b", b"1", b"1"])
    ret = c.SETBIT(*[b"b", b"1", b"0"])
    assert ret == protocolBuilder(1)

def test_getbit_check_getbit_return_value_on_non_existing_key():
    """Check GETBIT return value on non existing key"""
    c = _commands()
    ret = c.GETBIT(*[b"b", b"1"])
    assert ret == protocolBuilder(0)

def test_getbit_check_getbit_return_value_on_key():
    """Check GETBIT return value on key"""
    c = _commands()
    c.SETBIT(*[b"b", b"1", b"1"])
    ret = c.GETBIT(*[b"b", b"1"])
    assert ret == protocolBuilder(1)

def test_getbit_check_getbit_return_value_on_key_non_existing_bit():
    """Check GETBIT return value on key non existing bit"""
    c = _commands()
    c.SETBIT(*[b"b", b"2", b"1"])
    ret = c.GETBIT(*[b"b", b"100"])
    assert ret == protocolBuilder(0)

def test_bitop_check_bitop_return_value_for_and():
    """Check BITOP return value for AND"""
    c = _commands()
    c.SETBIT(*[b"b", b"10", b"1"])
    c.SETBIT(*[b"b", b"20", b"1"])
    c.SETBIT(*[b"b", b"30", b"1"])
    c.SETBIT(*[b"c", b"20", b"1"])
    c.SETBIT(*[b"c", b"30", b"1"])
    c.SETBIT(*[b"c", b"40", b"1"])
    c.SETBIT(*[b"d", b"30", b"1"])
    c.SETBIT(*[b"d", b"40", b"1"])
    c.SETBIT(*[b"d", b"50", b"1"])
    ret = c.BITOP(*[b"and", b"target", b"b", b"c", b"d"])
    assert ret == protocolBuilder(7)

def test_bitop_check_bitop_return_value_for_or():
    """Check BITOP return value for OR"""
    c = _commands()
    c.SETBIT(*[b"b", b"10", b"1"])
    c.SETBIT(*[b"b", b"20", b"1"])
    c.SETBIT(*[b"b", b"30", b"1"])
    c.SETBIT(*[b"c", b"20", b"1"])
    c.SETBIT(*[b"c", b"30", b"1"])
    c.SETBIT(*[b"c", b"40", b"1"])
    c.SETBIT(*[b"d", b"30", b"1"])
    c.SETBIT(*[b"d", b"40", b"1"])
    c.SETBIT(*[b"d", b"50", b"1"])
    ret = c.BITOP(*[b"or", b"target", b"b", b"c", b"d"])
    assert ret == protocolBuilder(7)

def test_bitop_check_bitop_return_value_for_xor():
    """Check BITOP return value for XOR"""
    c = _commands()
    c.SETBIT(*[b"b", b"10", b"1"])
    c.SETBIT(*[b"b", b"20", b"1"])
    c.SETBIT(*[b"b", b"30", b"1"])
    c.SETBIT(*[b"c", b"20", b"1"])
    c.SETBIT(*[b"c", b"30", b"1"])
    c.SETBIT(*[b"c", b"40", b"1"])
    c.SETBIT(*[b"d", b"30", b"1"])
    c.SETBIT(*[b"d", b"40", b"1"])
    c.SETBIT(*[b"d", b"50", b"1"])
    ret = c.BITOP(*[b"xor", b"target", b"b", b"c", b"d"])
    assert ret == protocolBuilder(7)

def test_bitop_check_bitop_return_value_for_not():
    """Check BITOP return value for NOT"""
    c = _commands()
    c.SETBIT(*[b"c", b"10", b"1"])
    c.SETBIT(*[b"c", b"20", b"1"])
    c.SETBIT(*[b"c", b"30", b"1"])
    ret = c.BITOP(*[b"not", b"target", b"c"])
    assert ret == protocolBuilder(4)

def test_bitcount_check_bitcount_return_value():
    """Check BITCOUNT return value """
    c = _commands()
    c.SETBIT(*[b"b", b"10", b"1"])
    c.SETBIT(*[b"b", b"20", b"1"])
    c.SETBIT(*[b"b", b"30", b"1"])
    c.SETBIT(*[b"b", b"301", b"1"])
    c.SETBIT(*[b"b", b"3000", b"1"])
    c.SETBIT(*[b"b", b"300000", b"1"])
    ret = c.BITCOUNT(*[b"b"])
    assert ret == protocolBuilder(6)

def test_bitcount_check_bitcount_return_value_for_nonexisting_key():
    """Check BITCOUNT return value for nonexisting key"""
    c = _commands()
    ret = c.BITCOUNT(*[b"b"])
    assert ret == protocolBuilder(0)

def test_bitpos_check_bitpos_1_return_value_for_existing_key():
    """Check BITPOS 1 return value for existing key"""
    c = _commands()
    c.SETBIT(*[b"b", b"10", b"1"])
    c.SETBIT(*[b"b", b"20", b"1"])
    c.SETBIT(*[b"b", b"30", b"1"])
    ret = c.BITPOS(*[b"b", b"1"])
    assert ret == protocolBuilder(10)

def test_bitpos_check_bitpos_0_return_value_for_existing_key():
    """Check BITPOS 0 return value for existing key"""
    c = _commands()
    c.SETBIT(*[b"b", b"0", b"1"])
    c.SETBIT(*[b"b", b"1", b"1"])
    c.SETBIT(*[b"b", b"2", b"1"])
    c.SETBIT(*[b"b", b"4", b"1"])
    ret = c.BITPOS(*[b"b", b"0"])
    assert ret == protocolBuilder(3)

def test_bitpos_check_bitpos_return_value_for_non_existing_key():
    """Check BITPOS  return value for non existing key"""
    c = _commands()
    ret = c.BITPOS(*[b"b", b"0"])
    assert ret == protocolBuilder(-1)
