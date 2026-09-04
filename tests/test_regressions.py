"""Regression tests for the reviewed-and-fixed areas:

- expiry coherence in Data (expired == missing on every read path)
- PERSIST / EXPIRE<=0 / TTL semantics
- type checking (WRONGTYPE instead of crashes / junk)
- negative offsets in GETRANGE, negative counters
- SPOP / SRANDMEMBER semantics, BITOP with missing sources
- RESP framing (partial reads, pipelining, CRLF inside bulk values)
- dispatch (unknown command / arity errors as -ERR replies)
- sqlite snapshot replace semantics
"""

from kagni.commands import Commands
from kagni.constants import Error, Response
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


def test_sscan_stub_removed():
    assert not hasattr(_commands(), "SSCAN")


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


# ---------------------------------------------------------------------- db
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
                db.dump(d)

                # deleting a key in memory must remove it from the store too
                del d[b"a"]
                db.dump(d)
                snapshot = db.load()
                assert set(snapshot) == {b"b"}, backend
                assert snapshot[b"b"] == b"2", backend

                db.flush()
                assert db.load() == {}, backend
        finally:
            dbmod.apsw = real_apsw
