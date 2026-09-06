"""Regression tests for the reviewed-and-fixed areas:

- expiry coherence in Data (expired == missing on every read path)
- PERSIST / EXPIRE<=0 / TTL semantics
- type checking (WRONGTYPE instead of crashes / junk)
- negative offsets in GETRANGE, negative counters
- SPOP / SRANDMEMBER semantics, BITOP with missing sources
- RESP framing (partial reads, pipelining, CRLF inside bulk values)
- dispatch (unknown command / arity errors as -ERR replies)
- sqlite snapshot replace semantics
- value updates keep the TTL (INCR/APPEND/SETRANGE/LTRIM/LREM), only
  the SET family clears it
- empty sets/hashes never persist (SREM/SPOP/SMOVE/HDEL/*STORE)
- FLUSHDB clears in place and stale snapshot commits stand down
- redis string2ll integer parsing (no '+', whitespace, leading zeros,
  64-bit range) and SCAN COUNT >= 1
- bare keyless calls (DEL/MGET/KEYS/SADD/SREM/HDEL) are arity errors
- SETBIT offset cap (512MB string limit)
"""

from kagni.commands import Commands
from kagni.constants import Error, Response, SimpleString
from kagni.data import Data
from kagni.resp import RESPReader, ProtocolError, protocolBuilder, protocolParser


def _readers():
    """One RESPReader per parse engine (pure python, plus hiredis when
    the optional C accelerator is installed)."""
    readers = [RESPReader(engine="python")]
    try:
        readers.append(RESPReader(engine="hiredis"))
    except ValueError:
        pass
    return readers


def _commands():
    return Commands(data=Data())


def _expect_error(callable_, class_="ERR"):
    try:
        callable_()
    except Error as exc:
        assert exc.class_ == class_, "expected %r error, got %r" % (class_, exc.class_)
        return exc
    raise AssertionError("expected an Error to be raised")


# ------------------------------------------------------------------ expiry
def test_expired_key_reads_as_missing():
    c = _commands()
    c.SET(b"k", b"v")
    c.EXPIRE(b"k", b"-1")
    # logically gone...
    assert c.GET(b"k") == protocolBuilder(Response.NIL)
    assert b"k" not in c.data
    assert c.data.get(b"k", b"default") == b"default"
    assert c.TTL(b"k") == protocolBuilder(-2)


def test_expired_key_excluded_from_keys_del_and_counters():
    c = _commands()
    c.SET(b"dead", b"x")
    c.EXPIRE(b"dead", b"-1")
    c.SET(b"live", b"y")
    assert c.KEYS(b"*") == protocolBuilder([b"live"])
    assert len(c.data) == 1

    # DEL on a logically-dead key reports 0 (redis semantics)
    c.SET(b"dead", b"x")
    c.EXPIRE(b"dead", b"-1")
    assert c.DEL(b"dead") == protocolBuilder(0)
    assert len(c.data) == 1

    # INCR on an expired key starts from 0 instead of crashing
    c.SET(b"e", b"5")
    c.EXPIRE(b"e", b"-1")
    assert c.INCR(b"e") == protocolBuilder(1)
    assert c.GET(b"e") == protocolBuilder(b"1")


def test_expire_zero_and_negative_delete_the_key():
    c = _commands()
    assert c.EXPIRE(b"missing", b"10") == protocolBuilder(0)

    c.SET(b"k", b"1")
    assert c.EXPIRE(b"k", b"0") == protocolBuilder(1)
    assert c.TTL(b"k") == protocolBuilder(-2)
    assert c.GET(b"k") == protocolBuilder(Response.NIL)

    c.SET(b"k", b"1")
    assert c.EXPIRE(b"k", b"-5") == protocolBuilder(1)
    assert c.GET(b"k") == protocolBuilder(Response.NIL)


def test_persist_clears_ttl_and_never_crashes():
    c = _commands()
    assert c.PERSIST(b"missing") == protocolBuilder(0)

    c.SET(b"k", b"1")
    assert c.EXPIRE(b"k", b"100") == protocolBuilder(1)
    assert c.PERSIST(b"k") == protocolBuilder(1)
    assert c.TTL(b"k") == protocolBuilder(-1)

    # persisting a logically-expired key reports 0 (and does not resurrect)
    c.SET(b"k", b"1")
    c.EXPIRE(b"k", b"-1")
    assert c.PERSIST(b"k") == protocolBuilder(0)
    assert c.GET(b"k") == protocolBuilder(Response.NIL)


def test_items_iteration_survives_expired_keys():
    d = Data()
    for i in range(5):
        d["k%d" % i] = b"x"
    d.expire("k0", -1)
    items = list(d.items())
    assert len(items) == 4
    assert all(key != "k0" for key, _ in items)
    assert len(d) == 4


# ---------------------------------------------------------- string commands
def test_getrange_negative_offsets():
    c = _commands()
    c.SET(b"k", b"hello world")
    assert c.GETRANGE(b"k", b"0", b"-1") == protocolBuilder(b"hello world")
    assert c.GETRANGE(b"k", b"-5", b"-1") == protocolBuilder(b"world")
    assert c.GETRANGE(b"k", b"6", b"10") == protocolBuilder(b"world")
    assert c.GETRANGE(b"k", b"3", b"1") == protocolBuilder(b"")
    assert c.GETRANGE(b"missing", b"0", b"-1") == protocolBuilder(b"")


def test_counters_accept_negative_values_and_reject_junk():
    c = _commands()
    assert c.DECR(b"n") == protocolBuilder(-1)
    assert c.INCR(b"n") == protocolBuilder(0)  # b"-1" must be accepted
    assert c.DECRBY(b"n", b"2") == protocolBuilder(-2)
    assert c.INCRBY(b"n", b"1") == protocolBuilder(-1)

    c.SET(b"abc", b"not a number")
    _expect_error(lambda: c.INCR(b"abc"))
    _expect_error(lambda: c.DECR(b"abc"))
    _expect_error(lambda: c.INCRBY(b"abc", b"1"))
    # int64 overflow
    c.SET(b"big", b"9223372036854775807")
    _expect_error(lambda: c.INCR(b"big"))


def test_mset_arity_and_pairs():
    _expect_error(lambda: _commands().MSET())
    _expect_error(lambda: _commands().MSET(b"a"))
    c = _commands()
    assert c.MSET(b"a", b"1", b"b", b"2") == protocolBuilder(Response.OK)
    assert c.data.get(b"a") == b"1"
    assert c.data.get(b"b") == b"2"


def test_wrongtype_raises_instead_of_crashing():
    c = _commands()
    c.HSET(b"h", b"f", b"v")
    _expect_error(lambda: c.GET(b"h"), "WRONGTYPE")
    _expect_error(lambda: c.APPEND(b"h", b"x"), "WRONGTYPE")
    _expect_error(lambda: c.STRLEN(b"h"), "WRONGTYPE")
    _expect_error(lambda: c.GETRANGE(b"h", b"0", b"-1"), "WRONGTYPE")
    _expect_error(lambda: c.SETRANGE(b"h", b"0", b"x"), "WRONGTYPE")
    _expect_error(lambda: c.INCR(b"h"), "WRONGTYPE")
    _expect_error(lambda: c.SADD(b"h", b"x"), "WRONGTYPE")

    c2 = _commands()
    c2.SET(b"s", b"abc")
    _expect_error(lambda: c2.HSET(b"s", b"f", b"v"), "WRONGTYPE")
    _expect_error(lambda: c2.SADD(b"s", b"x"), "WRONGTYPE")
    _expect_error(lambda: c2.SETBIT(b"s", b"1", b"1"), "WRONGTYPE")

    c3 = _commands()
    c3.SADD(b"set", b"m")
    _expect_error(lambda: c3.GET(b"set"), "WRONGTYPE")


def test_setrange_negative_offset_rejected():
    c = _commands()
    c.SET(b"k", b"hello")
    _expect_error(lambda: c.SETRANGE(b"k", b"-1", b"x"))


# --------------------------------------------------------------- set commands
def test_spop_removes_members():
    c = _commands()
    c.SADD(b"k", b"1", b"2", b"3")
    popped = protocolParser(c.SPOP(b"k", b"5"))
    assert sorted(popped) == [b"1", b"2", b"3"]
    assert c.SCARD(b"k") == protocolBuilder(0)
    assert c.SPOP(b"k") == protocolBuilder(Response.NIL)
    assert c.SPOP(b"k", b"1") == protocolBuilder([])
    _expect_error(lambda: c.SPOP(b"k", b"-1"))


def test_srandmember_counts_and_never_crashes():
    c = _commands()
    c.SADD(b"k", b"1", b"2", b"3")
    assert len(protocolParser(c.SRANDMEMBER(b"k", b"2"))) == 2
    assert len(protocolParser(c.SRANDMEMBER(b"k", b"-5"))) == 5
    assert len(protocolParser(c.SRANDMEMBER(b"k", b"0"))) == 0
    all_members = protocolParser(c.SRANDMEMBER(b"k", b"10"))
    assert sorted(all_members) == [b"1", b"2", b"3"]
    assert isinstance(protocolParser(c.SRANDMEMBER(b"k")), bytes)

    # one-member set with count > size must not blow up in random.sample
    c2 = _commands()
    c2.SADD(b"s", b"1")
    assert protocolParser(c2.SRANDMEMBER(b"s", b"3")) == [b"1"]
    assert c2.SRANDMEMBER(b"missing") == protocolBuilder(Response.NIL)
    assert c2.SRANDMEMBER(b"missing", b"3") == protocolBuilder([])


def test_sadd_deduplicates():
    c = _commands()
    assert c.SADD(b"k", b"a", b"a", b"b") == protocolBuilder(2)
    assert c.SCARD(b"k") == protocolBuilder(2)


# --------------------------------------------------------------- bit commands
def test_bitop_with_missing_sources_and_bad_ops():
    try:
        import pyroaring  # noqa: F401
    except ImportError:
        return
    c = _commands()
    c.SETBIT(b"a", b"10", b"1")
    # longest input is a (2 bytes); AND with a missing key is empty and
    # must not crash nor leave a stale destination behind
    assert c.BITOP(b"AND", b"dest", b"a", b"missing") == protocolBuilder(2)
    assert c.GETBIT(b"dest", b"10") == protocolBuilder(0)
    assert c.BITOP(b"OR", b"dest2", b"a", b"missing") == protocolBuilder(2)
    assert c.GETBIT(b"dest2", b"10") == protocolBuilder(1)
    # all sources missing -> 0
    assert c.BITOP(b"OR", b"dest3", b"nope1", b"nope2") == protocolBuilder(0)

    _expect_error(lambda: c.BITOP(b"NAND", b"d", b"a"))
    _expect_error(lambda: c.BITOP(b"NOT", b"d", b"a", b"a"))
    _expect_error(lambda: c.BITOP(b"AND", b"d"))


def test_bitpos_zero_finds_first_gap():
    try:
        import pyroaring  # noqa: F401
    except ImportError:
        return
    c = _commands()
    c.SETBIT(b"k", b"0", b"1")
    c.SETBIT(b"k", b"1", b"1")
    c.SETBIT(b"k", b"2", b"1")
    c.SETBIT(b"k", b"4", b"1")
    assert c.BITPOS(b"k", b"0") == protocolBuilder(3)


# --------------------------------------------------------------------- resp
def test_resp_reader_pipelining_and_fragmentation():
    for make in _readers():
        reader = make
        assert reader.engine in ("python", "hiredis")
        assert reader.feed(b"*1\r\n$4\r\nPIN") == []  # partial frame buffered
        assert reader.feed(b"G\r\n*1\r\n$4\r\nPING\r\n") == [
            [b"PING"],
            [b"PING"],
        ], reader.engine
        assert reader.feed(b"") == [], reader.engine


def test_resp_reader_crlf_inside_bulk_value():
    wire = b"*3\r\n$3\r\nSET\r\n$1\r\na\r\n$4\r\nx\r\ny\r\n"
    for reader in _readers():
        assert reader.feed(wire) == [[b"SET", b"a", b"x\r\ny"]], reader.engine


def test_resp_reader_malformed_payload():
    for reader in _readers():
        # invalid multibulk length: rejected by both engines
        try:
            reader.feed(b"*x\r\n")
        except ProtocolError:
            continue
        raise AssertionError("engine %s: expected ProtocolError" % reader.engine)


def test_resp_reader_bulk_terminator_strictness():
    """The pure engine requires the declared bulk length to be followed by
    CRLF; hiredis is lenient there (documented engine difference)."""
    wire = b"*1\r\n$3\r\nxxxxx"
    for reader in _readers():
        if reader.engine == "python":
            try:
                reader.feed(wire)
            except ProtocolError:
                continue
            raise AssertionError("python engine: expected ProtocolError")
        else:
            # hiredis parses the 3 declared bytes and leaves the tail
            # buffered for the next message
            assert reader.feed(wire) == [[b"xxx"]]


def test_resp_reader_inline_commands():
    """redis-benchmark's PING_INLINE test and telnet users send commands
    without RESP framing (e.g. ``PING\r\n``) — both engines must accept
    them at message boundaries."""
    for reader in _readers():
        assert reader.feed(b"PING\r\n") == [[b"PING"]], reader.engine
        assert reader.feed(b"PING\r\nSET foo bar\r\nPING\r\n") == [
            [b"PING"],
            [b"SET", b"foo", b"bar"],
            [b"PING"],
        ], reader.engine
        # fragmented inline command
        assert reader.feed(b"PIN") == [], reader.engine
        assert reader.feed(b"G\r\n") == [[b"PING"]], reader.engine


def test_resp_reader_inline_then_framed():
    for reader in _readers():
        wire = b"PING\r\n*1\r\n$4\r\nPING\r\n"
        assert reader.feed(wire) == [[b"PING"], [b"PING"]], reader.engine


def test_resp_reader_framed_then_inline():
    """Once hiredis has parsed every byte handed to it, the connection is
    back at a message boundary and inline commands must work again (mixed
    telnet/benchmark-style usage on one connection)."""
    for reader in _readers():
        assert reader.feed(b"*1\r\n$4\r\nPING\r\n") == [[b"PING"]], reader.engine
        assert reader.feed(b"PING\r\n") == [[b"PING"]], reader.engine
        # pipelined framed batch, then inline batch
        assert reader.feed(b"*1\r\n$4\r\nPING\r\n*1\r\n$4\r\nPING\r\n") == [
            [b"PING"],
            [b"PING"],
        ], reader.engine
        assert reader.feed(b"PING\r\nPING\r\n") == [
            [b"PING"],
            [b"PING"],
        ], reader.engine
        # partial framed frame completes, then inline again
        reader2 = RESPReader(engine=reader.engine)
        assert reader2.feed(b"*1\r\n$4\r\nPIN") == []
        assert reader2.feed(b"G\r\n") == [[b"PING"]], reader.engine
        assert reader2.feed(b"PING\r\n") == [[b"PING"]], reader.engine


def test_protocol_parser_one_shot_inline():
    assert protocolParser(b"PING\r\n") == [b"PING"]


def test_resp_reader_parse_variants():
    wire = (
        b":42\r\n"
        + b"$3\r\nfoo\r\n"
        + b"$-1\r\n"
        + b"*-1\r\n"
        + b"*0\r\n"
        + b"*2\r\n$1\r\na\r\n:7\r\n"
    )
    expected = [42, b"foo", None, None, [], [b"a", 7]]
    for reader in _readers():
        assert reader.feed(wire) == expected, reader.engine


def test_protocol_parser_one_shot():
    assert protocolParser(b"$3\r\nfoo\r\n") == b"foo"
    assert protocolParser(b":42\r\n") == 42
    assert protocolParser(b"*2\r\n$1\r\na\r\n$1\r\nb\r\n") == [b"a", b"b"]
    assert protocolParser(b"$-1\r\n") is None
    assert protocolParser(b"*0\r\n") == []
    try:
        protocolParser(b"*1\r\n$4\r\nPIN")
        raise AssertionError("expected ProtocolError")
    except ProtocolError:
        pass


def test_protocol_builder_roundtrip():
    for value in (b"hello", 42, [b"a", b"1"], []):
        assert protocolParser(protocolBuilder(value)) == value, value
    # simple strings are only produced outbound (the parser returns them
    # as raw lines including the type marker)
    assert protocolBuilder(Response.OK) == b"+OK\r\n"
    assert protocolBuilder(Response.PONG) == b"+PONG\r\n"
    assert protocolBuilder(Response.NIL) == b"$-1\r\n"
    assert protocolParser(protocolBuilder(Response.NIL)) is None


# ----------------------------------------------------------------- dispatch
def test_dispatch_unknown_command_and_arity():
    c = _commands()
    assert b"unknown command" in c.dispatch([b"FOOBAR"])
    assert b"wrong number of arguments" in c.dispatch([b"GET"])
    assert b"wrong number of arguments" in c.dispatch([b"GET", b"k", b"extra"])
    assert b"wrong number of arguments" in c.dispatch([b"MSET", b"a"])
    assert b"not an integer" in c.dispatch([b"EXPIRE", b"k", b"x"])
    assert c.dispatch([]) is None
    assert c.dispatch([b"PING"]) == protocolBuilder(Response.PONG)
    assert c.dispatch([b"SET", b"k", b"v"]) == protocolBuilder(Response.OK)
    assert c.dispatch([b"GET", b"k"]) == protocolBuilder(b"v")
    # an unknown command must not kill the handler for the next request
    assert c.dispatch([b"PING"]) == protocolBuilder(Response.PONG)


def test_config_get():
    c = _commands()
    # redis-benchmark probes exactly these two at startup
    assert c.dispatch([b"CONFIG", b"GET", b"save"]) == protocolBuilder(
        [b"save", b""]
    )
    assert c.dispatch([b"CONFIG", b"GET", b"appendonly"]) == protocolBuilder(
        [b"appendonly", b"no"]
    )
    assert c.dispatch([b"CONFIG", b"GET", b"maxmemory"]) == protocolBuilder(
        [b"maxmemory", b"0"]
    )
    # unknown parameter: empty array, like redis
    assert c.dispatch([b"CONFIG", b"GET", b"nope"]) == protocolBuilder([])
    # wildcard
    reply = protocolParser(c.dispatch([b"CONFIG", b"GET", b"*"]))
    assert reply == [
        b"appendonly", b"no", b"maxmemory", b"0",
        b"maxmemory-policy", b"noeviction", b"save", b"",
    ]
    # arity / unknown subcommand errors
    assert b"wrong number of arguments" in c.dispatch([b"CONFIG", b"GET"])
    reply = c.dispatch([b"CONFIG", b"SET", b"save", b"900 1"])
    assert b"Unknown CONFIG subcommand" in reply
    assert b"wrong number of arguments" in c.dispatch([b"CONFIG"])


# ---------------------------------------------------------------------- db
def test_list_wrongtype_raises():
    c = _commands()
    c.SET(b"s", b"abc")
    c.SADD(b"set", b"m")
    c.HSET(b"h", b"f", b"v")
    for key in (b"s", b"set", b"h"):
        _expect_error(lambda: c.LPUSH(key, b"x"), "WRONGTYPE")
        _expect_error(lambda: c.RPUSH(key, b"x"), "WRONGTYPE")
        _expect_error(lambda: c.LLEN(key), "WRONGTYPE")
        _expect_error(lambda: c.LRANGE(key, b"0", b"-1"), "WRONGTYPE")
        _expect_error(lambda: c.LINDEX(key, b"0"), "WRONGTYPE")
        _expect_error(lambda: c.LPOP(key), "WRONGTYPE")
        _expect_error(lambda: c.RPOP(key), "WRONGTYPE")
        _expect_error(lambda: c.LSET(key, b"0", b"x"), "WRONGTYPE")
        _expect_error(lambda: c.LTRIM(key, b"0", b"-1"), "WRONGTYPE")
        _expect_error(lambda: c.LREM(key, b"0", b"x"), "WRONGTYPE")
        _expect_error(lambda: c.LINSERT(key, b"BEFORE", b"p", b"x"), "WRONGTYPE")
    # ... and the reverse: list commands must not be usable on a list via
    # the wrong family either (spot-check)
    c2 = _commands()
    c2.RPUSH(b"lst", b"a")
    _expect_error(lambda: c2.GET(b"lst"), "WRONGTYPE")
    _expect_error(lambda: c2.SADD(b"lst", b"x"), "WRONGTYPE")


def test_lset_errors():
    c = _commands()
    _expect_error(lambda: c.LSET(b"missing", b"0", b"x"), "ERR")  # no such key
    c.RPUSH(b"k", b"a", b"b")
    err = _expect_error(lambda: c.LSET(b"k", b"5", b"x"))  # index out of range
    assert err.message == "index out of range", err.message
    _expect_error(lambda: c.LSET(b"k", b"-5", b"x"))


def test_linsert_where_validation_precedes_key_lookup():
    # redis validates BEFORE|AFTER before looking the key up
    c = _commands()
    err = _expect_error(lambda: c.LINSERT(b"missing", b"SIDEWAYS", b"p", b"x"))
    assert err.message == "syntax error", err.message


def test_pop_count_validation():
    c = _commands()
    for pop in (c.LPOP, c.RPOP):
        err = _expect_error(lambda: pop(b"missing", b"-1"))
        assert err.message == "value is out of range, must be positive", err.message
    # negative count on an existing list errors the same way
    c.RPUSH(b"k", b"a")
    _expect_error(lambda: c.LPOP(b"k", b"-3"))


def test_list_expiry_interplay():
    c = _commands()
    c.RPUSH(b"k", b"a", b"b")
    c.EXPIRE(b"k", b"-1")
    # logically gone: reads see nothing, pushes start a fresh list
    assert c.LLEN(b"k") == protocolBuilder(0)
    assert c.LRANGE(b"k", b"0", b"-1") == protocolBuilder([])
    assert c.LPOP(b"k") == protocolBuilder(Response.NIL)
    assert c.RPUSH(b"k", b"x") == protocolBuilder(1)
    assert c.LLEN(b"k") == protocolBuilder(1)


def test_nil_array_wire_shape():
    assert protocolBuilder(Response.NIL_ARRAY) == b"*-1\r\n"
    assert protocolParser(b"*-1\r\n") is None
    # empty array stays distinct from the null array
    assert protocolBuilder([]) == b"*0\r\n"


def test_dispatch_list_arity():
    c = _commands()
    assert b"wrong number of arguments" in c.dispatch([b"LPUSH", b"k"])
    assert b"wrong number of arguments" in c.dispatch([b"RPUSH", b"k"])
    assert b"wrong number of arguments" in c.dispatch([b"LPOP", b"k", b"1", b"2"])
    assert b"wrong number of arguments" in c.dispatch([b"LRANGE", b"k", b"0"])


def test_lpos_option_validation():
    c = _commands()
    c.RPUSH(b"k", b"a", b"b", b"a")
    # option parsing precedes key lookup: errors fire even on missing keys
    err = _expect_error(lambda: c.LPOS(b"missing", b"a", b"RANK"))
    assert err.message == "syntax error", err.message
    _expect_error(lambda: c.LPOS(b"missing", b"a", b"BOGUS", b"1"))
    err = _expect_error(lambda: c.LPOS(b"k", b"a", b"RANK", b"0"))
    assert err.message.startswith("RANK can't be zero"), err.message
    err = _expect_error(lambda: c.LPOS(b"k", b"a", b"COUNT", b"-1"))
    assert err.message == "COUNT can't be negative", err.message
    err = _expect_error(lambda: c.LPOS(b"k", b"a", b"MAXLEN", b"-1"))
    assert err.message == "MAXLEN can't be negative", err.message
    err = _expect_error(lambda: c.LPOS(b"k", b"a", b"RANK", b"x"))
    assert err.message == "value is not an integer or out of range", err.message


def test_lmove_validation_and_wrongtype():
    c = _commands()
    # where-arguments are parsed before any key lookup
    err = _expect_error(lambda: c.LMOVE(b"missing", b"dst", b"UP", b"LEFT"))
    assert err.message == "syntax error", err.message
    _expect_error(lambda: c.LMOVE(b"missing", b"dst", b"LEFT", b"SIDEWAYS"))

    # wrongtype matrix: source and destination are both checked
    c2 = _commands()
    c2.SET(b"s", b"abc")
    _expect_error(lambda: c2.LMOVE(b"s", b"dst", b"LEFT", b"LEFT"), "WRONGTYPE")
    c2.RPUSH(b"src", b"a")
    _expect_error(lambda: c2.LMOVE(b"src", b"s", b"LEFT", b"LEFT"), "WRONGTYPE")
    _expect_error(lambda: c2.RPOPLPUSH(b"s", b"dst"), "WRONGTYPE")
    # the destination type is checked before the source is popped
    c3 = _commands()
    c3.RPUSH(b"src", b"a", b"b")
    c3.HSET(b"h", b"f", b"v")
    _expect_error(lambda: c3.LMOVE(b"src", b"h", b"LEFT", b"LEFT"), "WRONGTYPE")
    assert list(c3.data[b"src"]) == [b"a", b"b"]


def test_type_command():
    c = _commands()
    assert c.TYPE(b"missing") == protocolBuilder(SimpleString("none"))
    assert protocolBuilder(SimpleString("none")) == b"+none\r\n"

    c2 = _commands()
    c2.RPUSH(b"lst", b"a")
    assert c2.TYPE(b"lst") == protocolBuilder(SimpleString("list"))
    c2.SET(b"s", b"v")
    assert c2.TYPE(b"s") == protocolBuilder(SimpleString("string"))
    c2.EXPIRE(b"s", b"-1")
    assert c2.TYPE(b"s") == protocolBuilder(SimpleString("none"))

    # bitmaps report "string", like redis (no bitmap type exists there)
    try:
        import pyroaring  # noqa: F401
    except ImportError:
        return
    c3 = _commands()
    c3.SETBIT(b"bm", b"3", b"1")
    assert c3.TYPE(b"bm") == protocolBuilder(SimpleString("string"))


def test_lmpop_validation():
    c = _commands()
    err = _expect_error(lambda: c.LMPOP(b"0", b"k", b"LEFT"))
    assert err.message == "numkeys should be greater than 0", err.message
    _expect_error(lambda: c.LMPOP(b"-1", b"k", b"LEFT"))
    err = _expect_error(lambda: c.LMPOP(b"1", b"k", b"LEFT", b"COUNT", b"0"))
    assert err.message == "count should be greater than 0", err.message
    err = _expect_error(lambda: c.LMPOP(b"1", b"k", b"LEFT", b"COUNT", b"-2"))
    assert err.message == "count should be greater than 0", err.message
    err = _expect_error(lambda: c.LMPOP(b"1", b"k", b"LEFT", b"RANK", b"1"))
    assert err.message == "syntax error", err.message
    # missing LEFT/RIGHT entirely, and key-count mismatches, are syntax errors
    _expect_error(lambda: c.LMPOP(b"1", b"k"))
    _expect_error(lambda: c.LMPOP(b"2", b"k", b"LEFT"))  # declares 2 keys, gives 1
    _expect_error(lambda: c.LMPOP(b"1", b"k", b"LEFT", b"extra"))
    # non-integer numkeys / count
    err = _expect_error(lambda: c.LMPOP(b"x", b"k", b"LEFT"))
    assert err.message == "value is not an integer or out of range", err.message


def test_lmpop_wrongtype():
    c = _commands()
    c.SET(b"s", b"abc")
    _expect_error(lambda: c.LMPOP(b"2", b"s", b"k2", b"LEFT"), "WRONGTYPE")
    # a wrongtype key later in the list is only an error if the scan
    # reaches it (earlier keys are missing/empty)
    c2 = _commands()
    c2.SET(b"s", b"abc")
    _expect_error(lambda: c2.LMPOP(b"2", b"k1", b"s", b"LEFT"), "WRONGTYPE")
    c3 = _commands()
    c3.SET(b"s", b"abc")
    c3.RPUSH(b"k1", b"x")
    # k1 has data, so the wrongtype k2 is never examined
    assert c3.LMPOP(b"2", b"k1", b"s", b"LEFT") == protocolBuilder([b"k1", [b"x"]])


def test_memory_mode_runtime():
    """--db :memory: must special-case to a real in-memory mode: sqlite
    memory databases live per connection, so dump/load can never
    round-trip, and running the snapshot machinery against them would
    just be busy-work.  build_runtime therefore returns no DB at all,
    which tells the engines to skip the dumper and final dump."""
    from kagni import cli
    from kagni.db import DB

    assert cli.is_memory_mode(":memory:")
    assert cli.is_memory_mode(None)
    assert not cli.is_memory_mode("kagni.sqlite")

    # prove the per-connection ephemerality that motivates the mode
    db = DB(":memory:")
    d = Data()
    d[b"a"] = b"1"
    db.dump(d)
    assert db.load() == {}

    db_, data_, handler_ = cli.build_runtime(":memory:")
    assert db_ is None
    assert data_ is not None
    assert handler_.persistence is None  # FLUSHDB only clears memory
    handler_.SET(b"k", b"v")
    assert handler_.GET(b"k") == protocolBuilder(b"v")


def test_no_save_mode_runtime():
    """--no-save: an existing snapshot is loaded at boot but never written
    back (redis' save ""), and a missing file is not created at all."""
    import os
    import tempfile

    from kagni import cli
    from kagni.db import DB

    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "seed.sqlite")

        # seed a snapshot the way a previous save-mode run would leave it
        seed = DB(path)
        d = Data()
        d[b"seed"] = b"yes"
        seed.dump(d)

        db_, data_, handler_ = cli.build_runtime(path, save=False)
        assert db_ is not None  # opened for the restore
        assert handler_.persistence is None  # FLUSHDB only clears memory
        assert handler_.GET(b"seed") == protocolBuilder(b"yes")
        handler_.SET(b"new", b"value")
        # nothing was written back
        assert set(DB(path).load()) == {b"seed"}

        # missing file + --no-save: start empty, create nothing on disk
        missing = os.path.join(tmp, "never.sqlite")
        db_, data_, handler_ = cli.build_runtime(missing, save=False)
        assert db_ is None
        assert handler_.GET(b"seed") == protocolBuilder(Response.NIL)
        assert not os.path.exists(missing)

        # sanity: save mode still creates the target file when missing
        db_, data_, handler_ = cli.build_runtime(missing, save=True)
        assert db_ is not None and os.path.exists(missing)


def test_set_option_validation():
    c = _commands()
    # syntax errors mirror redis parseExtendedStringArgumentsOrReply
    for options in (
        (b"NX", b"XX"), (b"XX", b"NX"), (b"EX", b"10", b"PX", b"10"),
        (b"PX", b"10", b"EX", b"10"), (b"EX", b"10", b"KEEPTTL"),
        (b"KEEPTTL", b"EX", b"10"), (b"EX",), (b"PX",), (b"BOGUS",),
        (b"PERSIST",),
    ):
        _expect_error(lambda: c.SET(b"k", b"v", *options))
    # duplicate flags are tolerated by redis (last one wins)
    assert c.SET(b"k", b"v", b"GET", b"GET") in (protocolBuilder(Response.NIL), protocolBuilder(b"v"))
    # GETEX: KEEPTTL and NX are SET-only
    _expect_error(lambda: c.GETEX(b"k", b"KEEPTTL"))
    _expect_error(lambda: c.GETEX(b"k", b"NX"))
    _expect_error(lambda: c.GETEX(b"k", b"EX"))  # option without a value

    # expire-time errors carry the command name
    err = _expect_error(lambda: c.SET(b"k", b"v", b"EX", b"0"))
    assert err.message == "invalid expire time in 'set' command", err.message
    _expect_error(lambda: c.SET(b"k", b"v", b"PX", b"-5"))
    _expect_error(lambda: c.SET(b"k", b"v", b"EX", b"x"))  # NOT_INT
    err = _expect_error(lambda: c.SETEX(b"k", b"0", b"v"))
    assert err.message == "invalid expire time in 'setex' command", err.message
    err = _expect_error(lambda: c.PSETEX(b"k", b"-1", b"v"))
    assert err.message == "invalid expire time in 'psetex' command", err.message


def test_getex_expiry_validation_order():
    c = _commands()
    # the TTL value is validated after the key lookup (redis behaviour):
    # a missing key replies nil even for an invalid expiry
    assert c.GETEX(b"missing", b"EX", b"0") == protocolBuilder(Response.NIL)
    c.SET(b"k", b"v")
    err = _expect_error(lambda: c.GETEX(b"k", b"EX", b"0"))
    assert err.message == "invalid expire time in 'getex' command", err.message


def test_set_get_and_ttl_edges():
    c = _commands()
    # NX failure leaves value AND ttl untouched
    c.SET(b"k", b"v", b"EX", b"100")
    assert c.SET(b"k", b"blocked", b"NX") == protocolBuilder(Response.NIL)
    assert c.GET(b"k") == protocolBuilder(b"v")
    assert c.TTL(b"k") == b":100\r\n"
    # XX on a logically expired key behaves like missing
    c2 = _commands()
    c2.SET(b"k", b"v", b"EXAT", b"1")  # past deadline: logically gone
    assert c2.SET(b"k", b"v2", b"XX") == protocolBuilder(Response.NIL)
    assert c2.SETNX(b"k", b"v3") == protocolBuilder(1)
    assert c2.EXISTS(b"k") == protocolBuilder(1)
    # KEEPTTL ignores a dead TTL
    c3 = _commands()
    c3.SET(b"k", b"v", b"EXAT", b"1")
    c3.SET(b"k", b"v2", b"KEEPTTL")
    assert c3.TTL(b"k") == protocolBuilder(-1)
    # EXAT/PXAT in the future set a working TTL
    import time as _wall

    c4 = _commands()
    c4.SET(b"k", b"v", b"EXAT", str(int(_wall.time()) + 3600).encode())
    assert c4.TTL(b"k") == b":3600\r\n"


def test_new_string_commands_wrongtype():
    c = _commands()
    c.RPUSH(b"lst", b"a")
    _expect_error(lambda: c.GETDEL(b"lst"), "WRONGTYPE")
    _expect_error(lambda: c.GETEX(b"lst"), "WRONGTYPE")
    _expect_error(lambda: c.SET(b"lst", b"x", b"GET"), "WRONGTYPE")
    # kind-agnostic commands do not raise
    c.HSET(b"h", b"f", b"v")
    assert c.EXISTS(b"h", b"lst") == protocolBuilder(2)
    assert c.TOUCH(b"h", b"lst") == protocolBuilder(2)
    assert c.SETNX(b"h", b"x") == protocolBuilder(0)  # exists -> no overwrite


def test_msetnx_and_exists_expiry():
    c = _commands()
    c.SET(b"k", b"v")
    c.EXPIRE(b"k", b"-1")
    # expired keys count as missing for MSETNX / EXISTS / SET NX
    assert c.MSETNX(b"k", b"v2", b"j", b"1") == protocolBuilder(1)
    assert c.GET(b"k") == protocolBuilder(b"v2")
    c2 = _commands()
    c2.SET(b"k", b"v")
    c2.EXPIRE(b"k", b"-1")
    assert c2.EXISTS(b"k") == protocolBuilder(0)
    assert c2.TOUCH(b"k") == protocolBuilder(0)
    # DBSIZE sweeps expired keys
    c3 = _commands()
    c3.SET(b"a", b"1")
    c3.SET(b"b", b"2", b"EXAT", b"1")
    assert c3.DBSIZE() == protocolBuilder(1)


def test_scan_validation_and_expiry():
    c = _commands()
    err = _expect_error(lambda: c.SCAN(b"abc"))
    assert err.message == "invalid cursor", err.message
    _expect_error(lambda: c.SCAN(b"-1"))
    _expect_error(lambda: c.SCAN(b"0", b"MATCH"))  # option without value
    _expect_error(lambda: c.SCAN(b"0", b"COUNT", b"x"))
    _expect_error(lambda: c.SCAN(b"0", b"BOGUS", b"1"))
    # a non-zero cursor finishes the (single-step) iteration
    assert c.SCAN(b"42") == protocolBuilder([b"0", []])
    # expired keys are not scanned
    c2 = _commands()
    c2.SET(b"dead", b"x")
    c2.EXPIRE(b"dead", b"-1")
    c2.SET(b"live", b"y")
    assert c2.SCAN(b"0") == protocolBuilder([b"0", [b"live"]])


def test_client_subcommand_errors():
    c = _commands()
    reply = c.dispatch([b"CLIENT", b"KILL", b"1"])
    assert b"Unknown subcommand" in reply, reply
    assert b"wrong number of arguments" in c.dispatch([b"CLIENT", b"SETNAME"])
    assert b"wrong number of arguments" in c.dispatch([b"CLIENT", b"SETINFO"])
    assert b"wrong number of arguments" in c.dispatch([b"CLIENT"])
    # valid shapes still work after the errors
    assert c.CLIENT(b"SETINFO", b"lib-ver", b"5.0") == protocolBuilder(Response.OK)


def test_incrbyfloat_validation():
    c = _commands()
    # invalid increments, mirroring redis string2ld: non-floats, nan,
    # whitespace, partials, overflow/underflow ("inf"/exponents are valid
    # parses and fail later only when the result is not finite)
    for bad in (b"abc", b"nan", b"", b"--1", b"1.2.3", b"1e-9999",
                b"1e9999", b" 1.5", b"1.5 ", b"1.5\xff"):
        err = _expect_error(lambda: c.INCRBYFLOAT(b"k", bad))
        assert err.message == "value is not a valid float", err.message
    # literal inf parses, but the infinite result is rejected
    err = _expect_error(lambda: c.INCRBYFLOAT(b"k", b"inf"))
    assert err.message == "increment would produce NaN or Infinity", err.message
    # exponents and signs are accepted like strtold
    assert c.INCRBYFLOAT(b"k", b"1e3") == protocolBuilder(b"1000")
    assert c.INCRBYFLOAT(b"k", b"1.5e1") == protocolBuilder(b"1015")
    assert c.INCRBYFLOAT(b"k", b"+1") == protocolBuilder(b"1016")
    assert c.INCRBYFLOAT(b"k", b"-.5") == protocolBuilder(b"1015.5")
    # a stored non-float value errors the same way
    c.SET(b"s", b"not-a-float")
    _expect_error(lambda: c.INCRBYFLOAT(b"s", b"1.5"))
    # type check happens before the increment is parsed (redis order)
    c.HSET(b"h", b"f", b"v")
    _expect_error(lambda: c.INCRBYFLOAT(b"h", b"not-a-float"), "WRONGTYPE")
    # overflow produces NaN/Infinity (increment as big as the stored max)
    import sys as _sys

    huge = format(_sys.float_info.max, "f").encode()
    c2 = _commands()
    c2.SET(b"big", huge)
    err = _expect_error(lambda: c2.INCRBYFLOAT(b"big", huge))
    assert err.message == "increment would produce NaN or Infinity", err.message


def test_incrbyfloat_formatting_contract():
    """Pins the formatter: shortest round-trip repr, no trailing '.0',
    -0 normalised to 0, exponents allowed, stored strings re-parse."""
    c = _commands()
    for increment, expected in ((b"10.5", b"10.5"), (b"-10.5", b"-10.5"),
                                (b"1e3", b"1000"), (b"-0.0", b"0")):
        c.SET(b"f", b"0")  # fresh base for every case
        assert c.INCRBYFLOAT(b"f", increment) == protocolBuilder(expected)
        # the stored string must re-parse for the next operation
        assert c.INCRBYFLOAT(b"f", b"0") == protocolBuilder(expected)
    # subtracting back to exactly zero prints '0', not '-0'
    c.SET(b"f", b"10.5")
    assert c.INCRBYFLOAT(b"f", b"-10.5") == protocolBuilder(b"0")
    # float precision case
    c2 = _commands()
    c2.SET(b"p", b"0.1")
    assert c2.INCRBYFLOAT(b"p", b"0.2") == protocolBuilder(b"0.30000000000000004")
    # large magnitudes use exponent notation (double repr); the stored
    # value must still parse for a subsequent operation
    c3 = _commands()
    c3.SET(b"big", b"123456789012345678901234567890")
    first = c3.INCRBYFLOAT(b"big", b"1")
    assert protocolParser(first).startswith(b"1.2345678901234568e+29")
    assert c3.INCRBYFLOAT(b"big", b"0") == first  # no-op roundtrip
    # double precision at 1e29 is ~1e13, so subtract a visible amount
    smaller = c3.INCRBYFLOAT(b"big", b"-1e22")
    assert smaller != first and protocolParser(smaller).startswith(b"1.2345677")


def test_transactions_multi_exec_discard():
    from kagni.commands import Session

    c = _commands()

    # basic flow: queue, +QUEUED replies, atomic-looking EXEC array
    s = Session()
    assert c.dispatch([b"MULTI"], s) == b"+OK\r\n"
    assert c.dispatch([b"SET", b"a", b"1"], s) == b"+QUEUED\r\n"
    assert c.dispatch([b"INCR", b"a"], s) == b"+QUEUED\r\n"
    assert c.dispatch([b"GET", b"a"], s) == b"+QUEUED\r\n"
    # queued commands see each other's effects (like redis)
    assert c.dispatch([b"EXEC"], s) == b"*3\r\n+OK\r\n:2\r\n$1\r\n2\r\n"
    # state is reset after EXEC
    assert c.dispatch([b"EXEC"], s) == b"-ERR EXEC without MULTI\r\n"

    # empty EXEC
    s2 = Session()
    c.dispatch([b"MULTI"], s2)
    assert c.dispatch([b"EXEC"], s2) == b"*0\r\n"

    # DISCARD drops the queue without executing
    s3 = Session()
    c.dispatch([b"MULTI"], s3)
    c.dispatch([b"SET", b"x", b"1"], s3)
    assert c.dispatch([b"DISCARD"], s3) == b"+OK\r\n"
    assert c.dispatch([b"GET", b"x"], s3) == b"$-1\r\n"
    assert c.dispatch([b"DISCARD"], s3) == b"-ERR DISCARD without MULTI\r\n"


def test_transactions_queue_time_and_runtime_errors():
    from kagni.commands import Session

    c = _commands()

    # nested MULTI
    s = Session()
    c.dispatch([b"MULTI"], s)
    assert c.dispatch([b"MULTI"], s) == b"-ERR MULTI calls can not be nested\r\n"
    # unknown commands and arity mistakes are answered immediately and
    # are NOT queued; MULTI stays open
    assert c.dispatch([b"FOOBAR"], s).startswith(b"-ERR unknown command")
    assert c.dispatch([b"GET"], s).startswith(b"-ERR wrong number")
    c.dispatch([b"SET", b"b", b"1"], s)
    assert c.dispatch([b"EXEC"], s) == b"*1\r\n+OK\r\n"
    assert c.dispatch([b"GET", b"b"], s) == b"$1\r\n1\r\n"

    # runtime errors become inline -ERR entries inside the EXEC array
    # while the remaining commands still run
    s2 = Session()
    c.dispatch([b"SET", b"bad", b"abc"], s2)
    c.dispatch([b"MULTI"], s2)
    c.dispatch([b"INCR", b"bad"], s2)
    c.dispatch([b"SET", b"ok", b"1"], s2)
    assert c.dispatch([b"EXEC"], s2) == (
        b"*2\r\n-ERR value is not an integer or out of range\r\n+OK\r\n"
    )
    assert c.dispatch([b"GET", b"ok"], s2) == b"$1\r\n1\r\n"

    # transactions are per-connection: another session is unaffected
    s3, s4 = Session(), Session()
    c.dispatch([b"MULTI"], s3)
    c.dispatch([b"SET", b"iso", b"queued"], s3)
    assert c.dispatch([b"GET", b"iso"], s4) == b"$-1\r\n"
    c.dispatch([b"DISCARD"], s3)
    assert c.dispatch([b"GET", b"iso"], s3) == b"$-1\r\n"


def test_set_expiry_unit_and_edge_coverage():
    import time as _wall

    c = _commands()
    # SET PX (milliseconds) - only EX/EXAT/PSETEX were covered before
    c.SET(b"k", b"v", b"PX", b"50000")
    assert c.TTL(b"k") == b":50\r\n"
    # SET PXAT (absolute ms), future
    c.SET(b"k", b"v", b"PXAT", str(int(_wall.time() * 1000) + 60000).encode())
    ttl = protocolParser(c.TTL(b"k"))
    assert 59 <= ttl <= 60, ttl
    # past PXAT: +OK reply, key logically gone
    assert c.SET(b"k", b"v", b"PXAT", b"1") == protocolBuilder(Response.OK)
    assert c.GET(b"k") == protocolBuilder(Response.NIL)
    # XX + GET on a missing key -> nil, key not created
    c2 = _commands()
    assert c2.SET(b"m", b"v", b"XX", b"GET") == protocolBuilder(Response.NIL)
    assert b"m" not in c2.data
    # NX on an existing wrong-type key -> NIL (not WRONGTYPE), hash intact
    c3 = _commands()
    c3.HSET(b"h", b"f", b"v")
    assert c3.SET(b"h", b"x", b"NX") == protocolBuilder(Response.NIL)
    assert c3.HGET(b"h", b"f") == protocolBuilder(b"v")
    # SETEX/PSETEX replace any existing kind, like redis
    c4 = _commands()
    c4.RPUSH(b"l", b"a")
    assert c4.SETEX(b"l", b"100", b"str") == protocolBuilder(Response.OK)
    assert c4.TYPE(b"l") == protocolBuilder(SimpleString("string"))
    c4.RPUSH(b"l2", b"a")
    assert c4.PSETEX(b"l2", b"100000", b"str") == protocolBuilder(Response.OK)
    assert c4.TYPE(b"l2") == protocolBuilder(SimpleString("string"))
    # GETEX without options leaves the TTL alone
    c5 = _commands()
    c5.SET(b"k", b"v", b"EX", b"100")
    assert c5.GETEX(b"k") == protocolBuilder(b"v")
    assert 0 < c5.data.ttl(b"k") <= 100
    # GETEX EXAT: future sets a TTL, past replies the value and deletes
    c6 = _commands()
    c6.SET(b"k", b"v")
    assert c6.GETEX(b"k", b"EXAT", str(int(_wall.time()) + 100).encode()) == protocolBuilder(b"v")
    assert c6.data.ttl(b"k") > 0
    c6.SET(b"k2", b"v2")
    assert c6.GETEX(b"k2", b"EXAT", b"1") == protocolBuilder(b"v2")
    assert c6.GET(b"k2") == protocolBuilder(Response.NIL)
    # GETEX PERSIST on a key without TTL stays a no-op
    c7 = _commands()
    c7.SET(b"k", b"v")
    assert c7.GETEX(b"k", b"PERSIST") == protocolBuilder(b"v")
    assert c7.data.ttl(b"k") == -1


def test_msetnx_arity_error():
    reply = _commands().dispatch([b"MSETNX", b"a"])
    assert b"wrong number of arguments" in reply, reply


def test_scan_option_details():
    c = _commands()
    c.SET(b"aaa", b"1")
    c.SET(b"aab", b"1")
    c.SET(b"bbb", b"1")
    c.RPUSH(b"ll", b"x")
    # COUNT is only a hint: valid values are ignored gracefully
    assert c.SCAN(b"0", b"COUNT", b"2") == protocolBuilder(
        [b"0", [b"aaa", b"aab", b"bbb", b"ll"]]
    )
    # repeated MATCH: the last one wins (redis behaviour)
    assert c.SCAN(b"0", b"MATCH", b"a*", b"MATCH", b"b*") == protocolBuilder(
        [b"0", [b"bbb"]]
    )
    # TYPE is case-insensitive and unknown types match nothing
    assert c.SCAN(b"0", b"TYPE", b"LIST") == protocolBuilder([b"0", [b"ll"]])
    assert c.SCAN(b"0", b"TYPE", b"string") == protocolBuilder(
        [b"0", [b"aaa", b"aab", b"bbb"]]
    )
    assert c.SCAN(b"0", b"TYPE", b"nope") == protocolBuilder([b"0", []])


def test_client_lowercase_subcommands():
    c = _commands()
    assert c.CLIENT(b"setinfo", b"lib-name", b"x") == protocolBuilder(Response.OK)
    assert c.CLIENT(b"setinfo", b"lib-ver", b"1.0") == protocolBuilder(Response.OK)
    assert c.CLIENT(b"setname", b"x") == protocolBuilder(Response.OK)
    assert c.CLIENT(b"getname") == protocolBuilder(b"")
    assert c.CLIENT(b"id") == protocolBuilder(1)


def test_transactions_nil_nested_and_lowercase():
    from kagni.commands import Session

    c = _commands()
    # EXEC array containing a nil entry
    s = Session()
    c.dispatch([b"MULTI"], s)
    c.dispatch([b"GET", b"missing"], s)
    c.dispatch([b"SET", b"ok", b"1"], s)
    assert c.dispatch([b"EXEC"], s) == b"*2\r\n$-1\r\n+OK\r\n"
    # nested array replies inside EXEC (queued LRANGE)
    s2 = Session()
    c.dispatch([b"MULTI"], s2)
    c.dispatch([b"RPUSH", b"l", b"a", b"b"], s2)
    c.dispatch([b"LRANGE", b"l", b"0", b"-1"], s2)
    assert c.dispatch([b"EXEC"], s2) == (
        b"*2\r\n:2\r\n*2\r\n$1\r\na\r\n$1\r\nb\r\n"
    )
    # lowercase command names work everywhere
    s3 = Session()
    assert c.dispatch([b"multi"], s3) == b"+OK\r\n"
    assert c.dispatch([b"set", b"a", b"1"], s3) == b"+QUEUED\r\n"
    assert c.dispatch([b"exec"], s3) == b"*1\r\n+OK\r\n"
    assert c.dispatch([b"discard"], s3) == b"-ERR DISCARD without MULTI\r\n"
    # transactions without a per-connection session are refused clearly
    assert c.dispatch([b"MULTI"]).startswith(b"-ERR MULTI requires")
    assert c.dispatch([b"EXEC"]) == b"-ERR EXEC without MULTI\r\n"


def test_db_snapshot_replace_semantics():
    """The snapshot backend must behave identically on apsw and on the
    stdlib sqlite3 fallback."""
    import os
    import tempfile

    import kagni.db as dbmod
    from kagni.db import DB

    real_apsw = dbmod.apsw
    backends = []
    if real_apsw is not None:
        backends.append("apsw")
    try:
        import sqlite3  # noqa: F401
        backends.append("sqlite3")
    except ImportError:
        pass
    assert backends, "no sqlite backend available"

    for backend in backends:
        if backend == "sqlite3":
            dbmod.apsw = None  # force the stdlib fallback
        try:
            with tempfile.TemporaryDirectory() as tmp:
                path = os.path.join(tmp, "kagni.sqlite")
                db = DB(path)
                d = Data()
                d[b"a"] = b"1"
                d[b"b"] = b"2"
                from collections import deque

                d[b"lst"] = deque([b"x", b"y"])
                db.dump(d)

                # deleting a key in memory must remove it from the store too
                del d[b"a"]
                db.dump(d)
                snapshot = db.load()
                assert set(snapshot) == {b"b", b"lst"}, backend
                assert snapshot[b"b"] == b"2", backend
                assert snapshot[b"lst"] == deque([b"x", b"y"]), backend

                db.flush()
                assert db.load() == {}, backend
        finally:
            dbmod.apsw = real_apsw


# ------------------------------------------- value updates keep the TTL (A2)
def test_value_updates_preserve_ttl():
    # redis keeps the TTL when a command updates a value in place; only
    # the SET family (SET/GETSET/SETEX/...) clears it
    c = _commands()
    c.SET(b"k", b"1", b"EX", b"100")
    c.INCR(b"k")
    assert c.data.ttl(b"k") > 0
    c.SET(b"a", b"abc", b"EX", b"100")
    c.APPEND(b"a", b"x")
    assert c.data.ttl(b"a") > 0
    c.SET(b"r", b"abc", b"EX", b"100")
    c.SETRANGE(b"r", b"1", b"X")
    assert c.data.ttl(b"r") > 0
    c.SET(b"f", b"1", b"EX", b"100")
    c.INCRBYFLOAT(b"f", b"0.5")
    assert c.data.ttl(b"f") > 0
    c.SET(b"d", b"10", b"EX", b"100")
    c.DECRBY(b"d", b"1")
    assert c.data.ttl(b"d") > 0
    # GETSET is part of the SET family: it clears the TTL
    c2 = _commands()
    c2.SET(b"g", b"abc", b"EX", b"100")
    c2.GETSET(b"g", b"z")
    assert c2.data.ttl(b"g") == -1


def test_list_trims_preserve_ttl():
    c = _commands()
    c.RPUSH(b"l", b"a", b"b", b"c")
    c.EXPIRE(b"l", b"100")
    c.LTRIM(b"l", b"0", b"1")
    assert c.data.ttl(b"l") > 0
    c2 = _commands()
    c2.RPUSH(b"l", b"a", b"b", b"a")
    c2.EXPIRE(b"l", b"100")
    c2.LREM(b"l", b"0", b"a")
    assert c2.data.ttl(b"l") > 0
    # removing the whole list deletes the key (and with it any TTL)
    c3 = _commands()
    c3.RPUSH(b"l", b"a")
    c3.EXPIRE(b"l", b"100")
    c3.LREM(b"l", b"0", b"a")
    assert c3.EXISTS(b"l") == protocolBuilder(0)


# --------------------------------------- empty collections never persist (A3)
def test_empty_collections_are_deleted():
    c = _commands()
    c.SADD(b"s", b"a")
    assert c.SREM(b"s", b"a") == protocolBuilder(1)
    assert c.EXISTS(b"s") == protocolBuilder(0)

    c2 = _commands()
    c2.SADD(b"s", b"a", b"b")
    assert sorted(protocolParser(c2.SPOP(b"s", b"5"))) == [b"a", b"b"]
    assert c2.EXISTS(b"s") == protocolBuilder(0)

    c3 = _commands()
    c3.SADD(b"s", b"a")
    assert c3.SPOP(b"s") == protocolBuilder(b"a")
    assert c3.EXISTS(b"s") == protocolBuilder(0)

    c4 = _commands()
    c4.HSET(b"h", b"f", b"v")
    assert c4.HDEL(b"h", b"f") == protocolBuilder(1)
    assert c4.EXISTS(b"h") == protocolBuilder(0)

    # a *STORE command whose result is empty deletes the destination,
    # whatever kind it held before
    c5 = _commands()
    c5.SET(b"dst", b"old")
    assert c5.SINTERSTORE(b"dst", b"missing", b"nope") == protocolBuilder(0)
    assert c5.EXISTS(b"dst") == protocolBuilder(0)
    assert c5.SUNIONSTORE(b"dst", b"missing") == protocolBuilder(0)
    assert c5.EXISTS(b"dst") == protocolBuilder(0)
    assert c5.SDIFFSTORE(b"dst", b"missing") == protocolBuilder(0)
    assert c5.EXISTS(b"dst") == protocolBuilder(0)


def test_smove_emptied_source_and_wrongtype_order():
    c = _commands()
    c.SADD(b"s", b"only")
    assert c.SMOVE(b"s", b"t", b"only") == protocolBuilder(1)
    assert c.EXISTS(b"s") == protocolBuilder(0)
    assert c.SMEMBERS(b"t") == protocolBuilder([b"only"])

    # a WRONGTYPE target errors before the member leaves the source
    c2 = _commands()
    c2.SADD(b"s", b"only")
    c2.SET(b"t", b"str")
    _expect_error(lambda: c2.SMOVE(b"s", b"t", b"only"), "WRONGTYPE")
    assert c2.SMEMBERS(b"s") == protocolBuilder([b"only"])


# ---------------------------------------- FLUSHDB and stale dumps (A1 + C1)
def test_flushdb_clears_in_place_and_stale_dumps_stand_down():
    import os
    import tempfile

    from kagni.db import DB

    c = _commands()
    c.SET(b"k", b"v")
    data = c.data
    assert c.FLUSHDB() == protocolBuilder(Response.OK)
    # in-place clear: the dumper's reference to the store (and the one
    # any test holds) sees the emptied state, not a swapped-in fresh Data
    assert data is c.data and len(data) == 0

    with tempfile.TemporaryDirectory() as tmp:
        db = DB(os.path.join(tmp, "k.sqlite"))
        d = Data()
        d[b"k"] = b"v"
        stale = d.snapshot()  # taken by the dumper before the flush
        epoch = d.epoch
        d.clear()  # FLUSHDB on the loop
        db.flush()  # FLUSHDB wipes the table
        # the in-flight commit from before the flush lands afterwards:
        # it must stand down, not resurrect the flushed key
        db.dump(stale, d, epoch)
        assert db.load() == {}
        # a fresh snapshot still commits normally
        db.dump(d.snapshot(), d, d.epoch)
        assert db.load() == {}


def test_snapshot_is_consistent_and_purges_corpses():
    from collections import deque

    d = Data()
    d[b"bytes"] = b"v"
    d[b"lst"] = deque([b"a", b"b"])
    d[b"h"] = {b"f": b"x"}
    d[b"s"] = {b"m"}
    snap = d.snapshot()
    # in-place command mutations after the snapshot must not tear it
    d[b"lst"].append(b"c")
    d[b"h"][b"g"] = b"y"
    d[b"s"].add(b"n")
    assert snap[b"lst"] == (deque([b"a", b"b"]), None)
    assert snap[b"h"] == ({b"f": b"x"}, None)
    assert snap[b"s"] == ({b"m"}, None)
    # expired corpses are dropped by the snapshot pass and purged
    d._storage[b"dead"] = {"value": b"x", "expires_at": 1}  # long past
    assert b"dead" not in d.snapshot()
    assert b"dead" not in d


# ------------------------------------------------- integer parsing (A4/B)
def test_integer_arguments_match_redis_parsing():
    c = _commands()
    # redis string2ll rejects '+', whitespace, underscores, leading zeros
    # and anything outside the signed 64-bit range
    for bad in (
        b"+5", b" 5", b"5 ", b"1_0", b"007", b"-0",
        b"9223372036854775808", b"99999999999999999999999999",
    ):
        _expect_error(lambda bad=bad: c.EXPIRE(b"k", bad))
        _expect_error(lambda bad=bad: c.INCRBY(b"k", bad))
        _expect_error(lambda bad=bad: c.GETRANGE(b"k", bad, b"0"))
    # valid forms keep working, including the int64 minimum
    assert c.EXPIRE(b"k", b"-5") == protocolBuilder(0)  # missing key
    c.INCRBY(b"n", b"-9223372036854775808")  # int64 minimum parses
    _expect_error(lambda: c.INCRBY(b"n", b"-1"))  # stepping below overflows


def test_scan_count_positive_only_and_strict_cursor():
    c = _commands()
    err = _expect_error(lambda: c.SCAN(b"0", b"COUNT", b"0"))
    assert err.message == "syntax error", err.message
    _expect_error(lambda: c.SCAN(b"0", b"COUNT", b"-1"))
    _expect_error(lambda: c.SCAN(b"0", b"COUNT", b"007"))
    err = _expect_error(lambda: c.SCAN(b"007"))
    assert err.message == "invalid cursor", err.message
    _expect_error(lambda: c.SCAN(b"+0"))
    assert c.SCAN(b"0", b"COUNT", b"2") == protocolBuilder([b"0", []])


# ------------------------------------------- bare keyless calls (B)
def test_bare_keyless_calls_are_arity_errors():
    c = _commands()
    for name in (b"DEL", b"MGET", b"KEYS", b"SADD", b"SREM", b"HDEL"):
        args = [b"k"] if name in (b"SADD", b"SREM", b"HDEL") else []
        assert b"wrong number of arguments" in c.dispatch([name] + args), name
    # a bare SADD must not create a live empty set
    c2 = _commands()
    assert b"wrong number of arguments" in c2.dispatch([b"SADD", b"k"])
    assert c2.EXISTS(b"k") == protocolBuilder(0)


# ------------------------------------------------------------ bit offsets
def test_setbit_offset_cap():
    try:
        import pyroaring  # noqa: F401
    except ImportError:
        return
    c = _commands()
    err = _expect_error(lambda: c.SETBIT(b"k", b"4294967296", b"1"))
    assert err.message == "bit offset is not an integer or out of range"
    assert c.SETBIT(b"k", b"4294967295", b"1") == protocolBuilder(0)


# ------------------------------------------------- hash family round-out
def test_hset_variadic_and_hash_reads():
    c = _commands()
    assert c.HSET(b"h", b"a", b"1", b"b", b"2") == protocolBuilder(2)
    assert c.HSET(b"h", b"a", b"x", b"c", b"3") == protocolBuilder(1)  # only c is new
    assert c.HGET(b"h", b"a") == protocolBuilder(b"x")
    assert c.HMGET(b"h", b"a", b"nope", b"c") == protocolBuilder(
        [b"x", Response.NIL, b"3"]
    )
    # a missing key replies one nil per requested field
    assert c.HMGET(b"noh", b"a", b"b") == protocolBuilder([Response.NIL, Response.NIL])
    assert c.HLEN(b"h") == protocolBuilder(3)
    assert c.HLEN(b"noh") == protocolBuilder(0)
    assert c.HKEYS(b"h") == protocolBuilder([b"a", b"b", b"c"])
    assert c.HVALS(b"h") == protocolBuilder([b"x", b"2", b"3"])
    assert c.HKEYS(b"noh") == protocolBuilder([])
    # arity: a field without a value, or no pairs at all
    assert b"wrong number of arguments" in c.dispatch([b"HSET", b"h", b"f"])
    assert b"wrong number of arguments" in c.dispatch([b"HSET", b"h"])
    assert b"wrong number of arguments" in c.dispatch([b"HMGET", b"h"])


def test_hincrby():
    c = _commands()
    assert c.HINCRBY(b"h", b"cnt", b"5") == protocolBuilder(5)
    assert c.HINCRBY(b"h", b"cnt", b"-2") == protocolBuilder(3)
    assert c.HINCRBY(b"h", b"cnt", b"-10") == protocolBuilder(-7)
    c2 = _commands()
    c2.HSET(b"h", b"txt", b"abc")
    err = _expect_error(lambda: c2.HINCRBY(b"h", b"txt", b"1"))
    assert err.message == "hash value is not an integer", err.message
    c3 = _commands()
    c3.HSET(b"h", b"big", b"9223372036854775807")
    _expect_error(lambda: c3.HINCRBY(b"h", b"big", b"1"))  # overflow
    c4 = _commands()
    c4.SET(b"s", b"x")
    _expect_error(lambda: c4.HINCRBY(b"s", b"f", b"1"), "WRONGTYPE")
    _expect_error(lambda: c4.HSET(b"s", b"f", b"v"), "WRONGTYPE")


# ----------------------------------------------------- expire family
def test_expire_family_ms_and_absolute():
    c = _commands()
    c.SET(b"k", b"v")
    assert c.PEXPIRE(b"k", b"100000") == protocolBuilder(1)
    assert 0 < protocolParser(c.PTTL(b"k")) <= 100000
    c2 = _commands()
    c2.SET(b"k", b"v")
    # a past absolute deadline deletes the key, like a non-positive TTL
    assert c2.EXPIREAT(b"k", b"1") == protocolBuilder(1)
    assert c2.EXISTS(b"k") == protocolBuilder(0)
    c3 = _commands()
    c3.SET(b"k", b"v")
    assert c3.PEXPIREAT(b"k", b"1") == protocolBuilder(1)
    assert c3.EXISTS(b"k") == protocolBuilder(0)
    # missing keys report 0 / -2, never create anything
    c4 = _commands()
    assert c4.PEXPIRE(b"nokey", b"100") == protocolBuilder(0)
    assert c4.EXPIREAT(b"nokey", b"9999999999") == protocolBuilder(0)
    assert c4.PTTL(b"nokey") == protocolBuilder(-2)
    assert c4.TTL(b"nokey") == protocolBuilder(-2)
    # strict integer parsing, like every typed argument
    _expect_error(lambda: c4.PEXPIRE(b"k", b"x"))
    _expect_error(lambda: c4.PEXPIRE(b"k", b"99999999999999999999999999"))
    _expect_error(lambda: c4.EXPIREAT(b"k", b"+5"))
    # relative ms expiry keeps sub-second precision
    c5 = _commands()
    c5.SET(b"k", b"v")
    c5.PEXPIRE(b"k", b"1500")
    assert 1400 < protocolParser(c5.PTTL(b"k")) <= 1500
    assert protocolParser(c5.TTL(b"k")) == 2  # rounds up like redis


def test_echo_and_info():
    c = _commands()
    assert c.ECHO(b"hello world") == protocolBuilder(b"hello world")
    assert c.ECHO(b"") == protocolBuilder(b"")

    c.SET(b"k", b"v")
    body = protocolParser(c.INFO())
    assert b"# Server" in body and b"redis_version:7.4.0" in body
    assert b"# Keyspace" in body and b"db0:keys=1,expires=0" in body
    assert protocolParser(c.INFO(b"server")).startswith(b"# Server")
    # unknown sections reply with an empty body, like redis
    assert protocolParser(c.INFO(b"nosuchsection")) == b""


# ------------------------------------------------------------- zset kinds
def test_zset_scan_type_and_snapshot():
    c = _commands()
    c.ZADD(b"z", b"1", b"a")
    assert c.TYPE(b"z") == protocolBuilder(SimpleString("zset"))
    assert c.SCAN(b"0", b"TYPE", b"zset") == protocolBuilder([b"0", [b"z"]])

    # the snapshot copies the container: later in-place writes must not
    # tear it, and pickling round-trips
    snap = c.data.snapshot()
    c.ZADD(b"z", b"2", b"b")
    c.data[b"z"].add(b"c", 3)
    assert len(snap[b"z"][0]) == 1
    c.ZADD(b"z2", b"9", b"m")
    snap2 = c.data.snapshot()
    c2 = _commands()
    c2.data.restore(snap2)
    assert c2.ZSCORE(b"z2", b"m") == protocolBuilder(b"9")


def test_zset_ttl_survives_in_place_ops():
    c = _commands()
    c.ZADD(b"z", b"1", b"a")
    c.EXPIRE(b"z", b"100")
    c.ZADD(b"z", b"2", b"b")  # additions mutate the stored set in place
    assert c.data.ttl(b"z") > 0
    c.ZINCRBY(b"z", b"1", b"a")
    c.ZREM(b"z", b"b")
    assert c.data.ttl(b"z") > 0
    # emptying the set deletes the key (and with it the TTL)
    c.ZPOPMIN(b"z")
    assert c.EXISTS(b"z") == protocolBuilder(0)


def test_zset_option_matrix_and_errors():
    c = _commands()
    c.ZADD(b"z", b"1", b"a", b"2", b"b")
    err = _expect_error(lambda: c.ZADD(b"z", b"NX", b"XX", b"1", b"a"))
    assert err.message == "XX and NX options at the same time are not compatible"
    _expect_error(lambda: c.ZADD(b"z", b"GT", b"LT", b"1", b"a"))
    _expect_error(lambda: c.ZADD(b"z", b"NX", b"GT", b"1", b"a"))
    err = _expect_error(lambda: c.ZADD(b"z", b"INCR", b"1", b"a", b"2", b"b"))
    assert err.message == "INCR option supports a single increment-element pair"
    _expect_error(lambda: c.ZADD(b"z", b"nan", b"a"))
    _expect_error(lambda: c.ZADD(b"z", b"1", b"a", b"2"))  # dangling score
    # NaN results (inf + -inf) error with redis' exact message
    c.ZADD(b"i", b"inf", b"m")
    err = _expect_error(lambda: c.ZINCRBY(b"i", b"-inf", b"m"))
    assert err.message == "resulting score is not a number (NaN)", err.message
    # option grammar errors
    _expect_error(lambda: c.ZRANGE(b"z", b"0", b"-1", b"LIMIT", b"0", b"1"))
    _expect_error(lambda: c.ZRANGE(b"z", b"0", b"-1", b"REV", b"REV"))
    _expect_error(lambda: c.ZRANGE(b"z", b"0", b"-1", b"BYSCORE", b"BYLEX"))
    err = _expect_error(lambda: c.ZRANGE(b"z", b"-", b"+", b"BYLEX", b"WITHSCORES"))
    assert err.message.endswith("not supported in combination with BYLEX")
    err = _expect_error(lambda: c.ZRANGE(b"z", b"abc", b"1", b"BYSCORE"))
    assert err.message == "min or max is not a float", err.message
    err = _expect_error(lambda: c.ZRANGEBYLEX(b"z", b"x", b"+"))
    assert err.message == "min or max not valid string range item", err.message
    _expect_error(lambda: c.ZRANGE(b"z", b"0", b"-1", b"BOGUS"))
    # degenerate lex windows are empty, not errors ('-' as max etc.)
    assert c.ZRANGEBYLEX(b"z", b"-", b"-") == protocolBuilder([])
    assert c.ZRANGEBYLEX(b"z", b"+", b"+") == protocolBuilder([])
    assert c.ZLEXCOUNT(b"z", b"-", b"-") == protocolBuilder(0)
    # bounds are validated before the key lookup
    _expect_error(lambda: c.ZCOUNT(b"missing", b"abc", b"1"))
    err = _expect_error(lambda: c.ZRANGE(b"missing", b"x", b"1", b"BYSCORE"))
    assert err.message == "min or max is not a float", err.message


def test_zset_wrongtype_and_store_edges():
    c = _commands()
    c.SET(b"s", b"x")
    for call in (
        lambda: c.ZADD(b"s", b"1", b"a"),
        lambda: c.ZRANGE(b"s", b"0", b"-1"),
        lambda: c.ZSCORE(b"s", b"a"),
        lambda: c.ZPOPMIN(b"s"),
        lambda: c.ZINCRBY(b"s", b"1", b"a"),
        lambda: c.ZUNIONSTORE(b"d", b"1", b"s"),
        lambda: c.ZRANK(b"s", b"a"),
    ):
        _expect_error(call, "WRONGTYPE")

    # numkeys framing errors carry redis' exact text
    err = _expect_error(lambda: c.ZUNIONSTORE(b"d", b"0", b"s"))
    assert err.message == "at least 1 input key is needed for 'zunionstore' command"
    err = _expect_error(lambda: c.ZDIFF(b"0", b"s"))
    assert err.message == "at least 1 input key is needed for 'zdiff' command"
    _expect_error(lambda: c.ZUNIONSTORE(b"d", b"2", b"s"))
    _expect_error(lambda: c.ZUNIONSTORE(b"d", b"1", b"s", b"WEIGHTS"))  # count mismatch
    err = _expect_error(lambda: c.ZUNIONSTORE(b"d", b"1", b"s", b"WEIGHTS", b"x"))
    assert err.message == "weight value is not a float", err.message
    _expect_error(lambda: c.ZUNIONSTORE(b"d", b"1", b"s", b"AGGREGATE", b"AVG"))
    # WITHSCORES is read-side only
    _expect_error(lambda: c.ZDIFFSTORE(b"d", b"1", b"s", b"WITHSCORES"))

    # a store whose result is empty deletes the destination; the result
    # never aliases a source key (self-union doubles the scores)
    c2 = _commands()
    c2.ZADD(b"a", b"1", b"x")
    c2.SET(b"dst", b"old")
    assert c2.ZINTERSTORE(b"dst", b"2", b"a", b"missing") == protocolBuilder(0)
    assert c2.EXISTS(b"dst") == protocolBuilder(0)
    assert c2.ZUNIONSTORE(b"a", b"1", b"a", b"WEIGHTS", b"2") == protocolBuilder(1)
    assert c2.ZSCORE(b"a", b"x") == protocolBuilder(b"2")
    # ZRANK: null array with WITHSCORE, null bulk without
    c3 = _commands()
    c3.ZADD(b"z", b"1", b"m")
    assert c3.ZRANK(b"z", b"nope") == protocolBuilder(Response.NIL)
    assert c3.ZRANK(b"z", b"nope", b"WITHSCORE") == protocolBuilder(
        Response.NIL_ARRAY
    )


def test_zset_persistence_roundtrip():
    import os
    import tempfile

    from kagni.db import DB

    with tempfile.TemporaryDirectory() as tmp:
        db = DB(os.path.join(tmp, "k.sqlite"))
        c = _commands()
        c.ZADD(b"z", b"1.5", b"a", b"2", b"b")
        c.HSET(b"h", b"f", b"v")
        db.dump(c.data.snapshot(), c.data, c.data.epoch)
        restored = db.load()
        c2 = Commands(data=Data())
        c2.data.restore(restored)
        assert c2.ZRANGE(b"z", b"0", b"-1", b"WITHSCORES") == protocolBuilder(
            [b"a", b"1.5", b"b", b"2"]
        )
        assert c2.ZADD(b"z", b"3", b"c") == protocolBuilder(1)
        assert c2.HGET(b"h", b"f") == protocolBuilder(b"v")


# ------------------------------------------- expiry survives snapshots
def test_expiry_persists_across_snapshot_restore():
    import os
    import tempfile

    from kagni.db import DB

    c = _commands()
    c.SET(b"eternal", b"v")          # no TTL: stays eternal
    c.SET(b"short", b"v", b"EX", b"100")
    c.SET(b"ms", b"v")
    c.PEXPIRE(b"ms", b"1500")
    c.RPUSH(b"lst", b"a")
    c.EXPIRE(b"lst", b"50")
    with tempfile.TemporaryDirectory() as tmp:
        db = DB(os.path.join(tmp, "k.sqlite"))
        db.dump(c.data.snapshot(), c.data, c.data.epoch)

        # fresh boot: restore re-arms the monotonic deadlines
        restored = Data()
        restored.restore(db.load())
        assert restored.get(b"eternal") == b"v"
        assert restored.ttl(b"eternal") == -1
        assert restored.get(b"short") == b"v"
        assert 0 < restored.ttl(b"short") <= 100
        assert 1000 < restored.ttl_ms(b"ms") <= 1500
        assert 0 < restored.ttl(b"lst") <= 50

    # a key whose deadline passed while the server was down is dropped,
    # like redis discarding expired keys on load
    d = Data()
    d[b"k"] = b"v"
    snap = d.snapshot()
    snap[b"k"] = (b"v", 1)  # deadline in the distant past
    restored = Data()
    restored.restore(snap)
    assert len(restored) == 0

    # legacy snapshots (plain values, written before expiry persistence)
    # still restore, without a TTL
    legacy = {b"old": b"value"}
    restored2 = Data()
    restored2.restore(legacy)
    assert restored2.get(b"old") == b"value"
    assert restored2.ttl(b"old") == -1


# ------------------------------------------------------- COMMAND metadata
def test_command_metadata_replies():
    c = _commands()
    # bare COMMAND: per-command entries with redis' (name, arity, flags)
    # shape; write/read-only classification included
    table = protocolParser(c.COMMAND())
    assert isinstance(table, list)
    by_name = {entry[0]: entry for entry in table if isinstance(entry, list)}
    assert by_name[b"GET"][1] == 2 and by_name[b"GET"][2] == [b"readonly"]
    assert by_name[b"SET"][1] == -3 and by_name[b"SET"][2] == [b"write"]
    assert by_name[b"FLUSHALL"][2] == [b"write", b"admin"]
    assert by_name[b"PING"][2] == []  # neither read-only nor a write
    assert by_name[b"ZUNIONSTORE"][2] == [b"write"]

    count = protocolParser(c.COMMAND(b"COUNT"))
    assert count == len(table) and count > 100

    # DOCS: flat [name, map] pairs, filtered by the requested names
    docs = protocolParser(c.COMMAND(b"DOCS", b"get", b"nosuchcmd"))
    assert docs == [
        [b"GET", [b"summary", b"", b"since", b"0.9.0", b"group", b"string",
                  b"arity", 2, b"flags", [b"readonly"]]]
    ]
    # all docs when no names are given
    everything = protocolParser(c.COMMAND(b"DOCS"))
    assert len(everything) == count
    # unknown subcommands error like the other admin commands
    assert b"Unknown subcommand" in c.dispatch([b"COMMAND", b"BOGUS"])


# ------------------------------------------------------------ HELLO/RESP2
def test_hello_negotiates_resp2_only():
    c = _commands()
    reply = protocolParser(c.HELLO())
    assert reply == [
        b"server", b"redis", b"version", b"7.4.0", b"proto", 2,
        b"id", 1, b"mode", b"standalone", b"role", b"master",
        b"modules", [],
    ]
    reply2 = protocolParser(c.HELLO(b"2", b"SETNAME", b"cli"))
    assert reply2[reply2.index(b"proto") + 1] == 2
    err = _expect_error(lambda: c.HELLO(b"3"), "NOPROTO")
    assert err.message == "unsupported protocol version"
    _expect_error(lambda: c.HELLO(b"2", b"AUTH", b"user", b"pass"))  # no password


# -------------------------------------------------- collection scans
def test_collection_scans_one_step_semantics():
    c = _commands()
    c.HSET(b"h", b"f1", b"v1", b"f2", b"v2", b"other", b"x")
    c.SADD(b"s", b"aa", b"ab", b"bb")
    c.ZADD(b"z", b"1", b"m1", b"2", b"m2", b"3", b"other")

    cursor, items = protocolParser(c.HSCAN(b"h", b"0"))
    assert cursor == b"0" and sorted(items) == sorted(
        [b"f1", b"v1", b"f2", b"v2", b"other", b"x"]
    )
    cursor, items = protocolParser(c.HSCAN(b"h", b"0", b"MATCH", b"f*"))
    assert cursor == b"0" and sorted(items) == sorted([b"f1", b"v1", b"f2", b"v2"])
    # any cursor answers with the full match set and cursor 0, like the
    # one-step keyspace SCAN (redis also answers non-zero cursors)
    assert protocolParser(c.HSCAN(b"h", b"42", b"MATCH", b"f*")) == [
        b"0", [b"f1", b"v1", b"f2", b"v2"]
    ]

    cursor, members = protocolParser(c.SSCAN(b"s", b"0"))
    assert cursor == b"0" and set(members) == {b"aa", b"ab", b"bb"}
    assert protocolParser(c.SSCAN(b"s", b"0", b"MATCH", b"a*"))[1] == [b"aa", b"ab"] or \
        sorted(protocolParser(c.SSCAN(b"s", b"0", b"MATCH", b"a*"))[1]) == [b"aa", b"ab"]

    # zscan replies in rank order, member/score interleaved
    assert protocolParser(c.ZSCAN(b"z", b"0")) == [
        b"0",
        [b"m1", b"1", b"m2", b"2", b"other", b"3"],
    ]
    assert protocolParser(c.ZSCAN(b"z", b"0", b"MATCH", b"m*")) == [
        b"0", [b"m1", b"1", b"m2", b"2"]
    ]

    # missing keys scan empty; wrong kinds raise WRONGTYPE
    assert protocolParser(c.HSCAN(b"noh", b"0")) == [b"0", []]
    assert protocolParser(c.SSCAN(b"nos", b"0")) == [b"0", []]
    assert protocolParser(c.ZSCAN(b"noz", b"0")) == [b"0", []]
    c.SET(b"str", b"x")
    for call in (
        lambda: c.HSCAN(b"str", b"0"),
        lambda: c.SSCAN(b"str", b"0"),
        lambda: c.ZSCAN(b"str", b"0"),
    ):
        _expect_error(call, "WRONGTYPE")

    # argument validation mirrors SCAN
    err = _expect_error(lambda: c.HSCAN(b"h", b"abc"))
    assert err.message == "invalid cursor", err.message
    _expect_error(lambda: c.SSCAN(b"s", b"-1"))
    _expect_error(lambda: c.ZSCAN(b"z", b"0", b"COUNT", b"0"))
    _expect_error(lambda: c.ZSCAN(b"z", b"0", b"COUNT", b"x"))
    _expect_error(lambda: c.HSCAN(b"h", b"0", b"BOGUS", b"1"))
    _expect_error(lambda: c.HSCAN(b"h", b"0", b"MATCH"))
    # TYPE is a keyspace-SCAN-only option
    _expect_error(lambda: c.HSCAN(b"h", b"0", b"TYPE", b"hash"))
