"""redis-py driving a real kagni server: the client-ecosystem view.

Everything else validates kagni from the inside (wire parity, command
batteries); these tests prove the pitch from the outside - the most
used redis client works against kagni over a real socket.  Each test
starts from a flushed store.
"""

import pytest

redis = pytest.importorskip("redis")


@pytest.fixture
def r(kagni_server):
    # protocol=2: kagni speaks RESP2 (redis-py >= 8 defaults to HELLO 3,
    # which kagni answers with NOPROTO)
    client = redis.Redis(
        host=kagni_server.host, port=kagni_server.port, protocol=2
    )
    client.flushdb()
    yield client
    client.close()


def test_strings(r):
    assert r.set("k", "v")
    assert r.get("k") == b"v"
    assert r.set("n", 1, nx=True) and r.set("n", 2, nx=True) is None
    assert r.get("n") == b"1"
    assert r.set("x", "v", ex=100)
    assert 0 < r.ttl("x") <= 100
    assert r.set("k", "v2", xx=True)  # xx on an existing key
    assert r.set("nokey", "v", xx=True) is None
    assert r.incr("c") == 1 and r.incrby("c", 4) == 5 and r.decr("c") == 4
    assert r.incrbyfloat("f", 1.5) == 1.5
    assert r.append("a", "bc") == 2 and r.get("a") == b"bc"
    assert r.strlen("a") == 2
    assert r.setrange("a", 1, "X") == 2 and r.get("a") == b"bX"
    assert r.getrange("a", 0, 0) == b"b"
    assert r.mset({"m1": "1", "m2": "2"})
    assert r.mget("m1", "nope", "m2") == [b"1", None, b"2"]
    assert r.getdel("a") == b"bX" and r.get("a") is None
    assert r.getset("g", "1") is None and r.get("g") == b"1"
    assert r.getex("g") == b"1"
    assert r.setnx("s", "v") and r.setnx("s", "w") is False
    assert r.set("se", "v", ex=100) and 0 < r.ttl("se") <= 100
    assert r.psetex("pse", 1000, "v") and 0 < r.pttl("pse") <= 1000


def test_keyspace(r):
    r.mset({"a": "1", "b": "2", "c": "3"})
    assert r.exists("a", "nope", "c") == 2
    assert r.type("a") == b"string"
    assert r.dbsize() == 3
    assert r.expire("a", 100) and r.ttl("a") > 0
    assert r.pexpire("b", 1000) and r.pttl("b") > 0
    assert sorted(r.keys("a*")) == [b"a"]
    assert set(r.scan_iter(match="*", count=1)) == {b"a", b"b", b"c"}
    assert r.persist("a") and r.ttl("a") == -1
    assert r.delete("b") == 1 and r.delete("b") == 0
    assert r.touch("c") == 1


def test_lists(r):
    assert r.rpush("l", "a", "b") == 2
    assert r.lpush("l", "z") == 3
    assert r.llen("l") == 3
    assert r.lrange("l", 0, -1) == [b"z", b"a", b"b"]
    assert r.lindex("l", 1) == b"a" and r.lindex("l", -1) == b"b"
    assert r.lset("l", 0, "y") is True
    assert r.linsert("l", "AFTER", "a", "m") == 4
    assert r.lrem("l", 1, "m") == 1
    assert r.lpushx("l", "w") == 4 and r.lpushx("nokey", "w") == 0
    assert r.rpoplpush("l", "l2") == b"b"
    assert r.lpop("l") == b"w" and r.rpop("l") == b"a"
    assert r.ltrim("l", 0, 0) is True
    assert r.lrange("l", 0, -1) == [b"y"]
    assert r.lpos("l", "y") == 0
    # moved element disappears from the source
    r.rpush("s", "1", "2")
    assert r.lmove("s", "d", "LEFT", "RIGHT") == b"1"
    assert r.lrange("s", 0, -1) == [b"2"]
    assert r.lmpop(2, "s", "nokey", direction="RIGHT") == [b"s", [b"2"]]


def test_sets(r):
    assert r.sadd("s", "a", "b") == 2
    assert r.sadd("s", "a") == 0
    assert r.scard("s") == 2
    assert r.sismember("s", "a") == 1 and r.sismember("s", "nope") == 0
    assert r.smembers("s") == {b"a", b"b"}
    # random-ish pops on dedicated keys so the algebra below stays exact
    assert r.sadd("pop", "a", "b", "c")
    assert r.spop("pop") in (b"a", b"b", b"c")
    popped = r.spop("pop", 2)
    assert len(popped) == 2
    assert r.srandmember("s", 1)[0] in (b"a", b"b")
    assert r.srandmember("s", -3)  # repetition allowed
    # smove with a dedicated source keeps every assertion deterministic
    assert r.sadd("mv", "a") == 1
    assert r.smove("mv", "s", "a") == 1 and r.sismember("s", "a") == 1
    assert r.exists("mv") == 0  # emptied source vanishes
    assert r.sadd("t", "b", "d")
    assert r.sdiff("s", "t") == {b"a"}
    assert r.sinter("s", "t") == {b"b"}
    assert r.sunion("s", "t") == {b"a", b"b", b"d"}
    assert r.sdiffstore("dst", "s", "t") == 1
    assert r.sinterstore("dst2", "s", "t") == 1
    assert r.sunionstore("dst3", "s", "t") == 3
    assert r.srem("t", "b", "d") == 2 and r.scard("t") == 0
    assert r.exists("t") == 0  # emptied sets vanish, like redis


def test_hashes(r):
    assert r.hset("h", "f1", "v1") == 1
    assert r.hset("h", mapping={"f2": "v2", "f3": "v3"}) == 2
    assert r.hget("h", "f1") == b"v1"
    assert r.hmget("h", "f1", "nope", "f3") == [b"v1", None, b"v3"]
    assert r.hgetall("h") == {b"f1": b"v1", b"f2": b"v2", b"f3": b"v3"}
    assert r.hlen("h") == 3
    assert r.hexists("h", "f1") == 1
    assert r.hkeys("h") == [b"f1", b"f2", b"f3"]
    assert r.hvals("h") == [b"v1", b"v2", b"v3"]
    assert r.hincrby("h", "cnt", 5) == 5 and r.hincrby("h", "cnt", -2) == 3
    assert r.hdel("h", "f1", "nope") == 1 and r.hlen("h") == 3
    assert r.hget("noh", "f") is None and r.hmget("noh", "a", "b") == [None, None]


def test_sorted_sets(r):
    assert r.zadd("z", {"a": 1, "b": 2}) == 2
    assert r.zadd("z", {"a": 3}) == 0
    assert r.zscore("z", "a") == 3.0
    assert r.zmscore("z", ["a", "nope"]) == [3.0, None]
    assert r.zcard("z") == 2
    assert r.zrank("z", "b") == 0 and r.zrevrank("z", "b") == 1
    assert r.zincrby("z", 2, "a") == 5.0
    assert r.zrange("z", 0, -1) == [b"b", b"a"]
    assert r.zrange("z", 0, -1, withscores=True) == [(b"b", 2.0), (b"a", 5.0)]
    assert r.zrevrange("z", 0, 0) == [b"a"]
    assert r.zrangebyscore("z", 2, 5) == [b"b", b"a"]
    assert r.zrangebyscore("z", "(2", 5, withscores=True) == [(b"a", 5.0)]
    assert r.zcount("z", "-inf", "+inf") == 2
    assert r.zadd("lex", mapping={"a": 0, "b": 0, "c": 0, "d": 0})
    assert r.zrangebylex("lex", "[b", "(d") == [b"b", b"c"]
    assert r.zlexcount("lex", "-", "+") == 4
    assert r.zrem("z", "a") == 1
    assert r.zpopmin("lex") == [(b"a", 0.0)]
    assert r.zpopmax("lex", 2) == [(b"d", 0.0), (b"c", 0.0)]
    assert r.zadd("u1", {"x": 1, "y": 2}) == 2
    assert r.zadd("u2", {"y": 3, "z": 4}) == 2
    assert r.zunionstore("u", ["u1", "u2"]) == 3
    assert r.zrange("u", 0, -1, withscores=True) == [
        (b"x", 1.0), (b"z", 4.0), (b"y", 5.0)
    ]
    assert r.zinterstore("i", ["u1", "u2"]) == 1
    assert r.zscore("i", "y") == 5.0
    assert r.zrandmember("u1") in (b"x", b"y")
    assert r.zadd("one", {"only": 9.0}) == 1
    assert r.zpopmax("one") == [(b"only", 9.0)]
    assert r.exists("one") == 0  # emptied zsets vanish, like redis


def test_bitmaps(r):
    assert r.setbit("b", 7, 1) == 0
    assert r.getbit("b", 7) == 1 and r.getbit("b", 6) == 0
    assert r.bitcount("b") == 1
    assert r.bitpos("b", 1) == 7
    assert r.setbit("b2", 0, 1) == 0
    assert r.bitop("AND", "dst", "b", "b2") == 1
    assert r.getbit("dst", 0) == 0


def test_expire_family_and_echo(r):
    assert r.set("k", "v")
    assert r.pexpire("k", 1500)
    assert 1000 < r.pttl("k") <= 1500
    assert r.expireat("k", 4102444800)  # far future
    assert r.ttl("k") > 0
    assert r.pexpireat("k", 4102444800000)
    assert r.pttl("k") > 0
    assert r.persist("k") and r.pttl("k") == -1
    assert r.echo("hello") == b"hello"


def test_pipelines_and_transactions(r):
    pipe = r.pipeline(transaction=False)
    pipe.set("a", "1").incr("a").get("a")
    assert pipe.execute() == [True, 2, b"2"]

    # MULTI/EXEC over the wire: atomic batch, results as a list
    pipe = r.pipeline(transaction=True)
    pipe.set("t1", "v1").set("t2", "v2").get("t1")
    assert pipe.execute() == [True, True, b"v1"]


def test_info_and_ping(r):
    assert r.ping() is True
    info = r.info("server")
    assert info["redis_version"] == "7.4.0"
    assert info["redis_mode"] == "standalone"
    r.set("k", "v")
    keyspace = r.info("keyspace")
    assert keyspace["db0"]["keys"] == 1


def test_resp3_probe_fails_cleanly(kagni_server):
    # redis-py >= 8 defaults to HELLO 3; kagni speaks RESP2 and must
    # answer NOPROTO rather than hang or corrupt the stream
    client = redis.Redis(
        host=kagni_server.host, port=kagni_server.port, protocol=3
    )
    try:
        with pytest.raises(redis.exceptions.ResponseError) as exc:
            client.ping()
        assert "NOPROTO" in str(exc.value)
    finally:
        client.close()
