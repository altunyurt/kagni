# kagni

Kagni is a Python-native, Redis-protocol data store daemon: everything in
memory, snapshots to sqlite, one `pip install` away. Named after the Turkish
ox-cart (kağnı) - not built for raw speed, but it gets things done.

## Why kagni

It is a real RESP server that lives comfortably inside Python workflows:

- **Testing / CI** - a genuine Redis-compatible endpoint over TCP or a unix
  socket for integration tests: real wire protocol, real pipelining, real
  persistence modes, no containers and no native builds. For component
  tests the command layer is importable directly, no sockets needed.
  (Alternatives like fakeredis run in-process only and speak no sockets.)
- **Embedded** - `kagni.embed` runs the server inside your own event loop
  (asyncio or trio), no subprocess; or run it as a sidecar daemon next to
  your service (`--db :memory:` for a pure-RAM cache, a sqlite snapshot
  file for durability, `--no-save` to serve a seed dataset without ever
  writing back).
- **Native Python** - `pip install .` then `kagni` or `python -m kagni`;
  pick the event loop (asyncio+uvloop or trio); sqlite snapshots are
  inspectable with standard tooling.

It is not a Redis replacement where throughput or feature breadth matter:
expect a modest single-process op rate, the 153 commands below, and no
blocking commands, replication or streams. Redis 7.4 (LTS) is the
compatibility target - the implemented subset behaves identically in 8.x.

## Running

Requires Python 3.11+ (developed on 3.13).

```
uv sync                    # install deps and the `kagni` console script
uv run kagni --help        # or: uv run python -m kagni
pip install .              # plain-pip alternative; then: kagni --help

kagni --loop asyncio|trio [--host HOST] [--port PORT] [--socket PATH]
      [--db PATH] [--dump-interval SECS] [--no-save] [--no-uvloop]
      [--daemon] [--pidfile PATH] [--logfile PATH]
```

Defaults: `asyncio` loop (uvloop when installed), `localhost:6379` (redis'
port; pass `--port` to run alongside a real redis), sqlite file
`kagni.sqlite`, snapshot every 20 s.

- TCP and a unix domain socket are additive: `--socket PATH` also listens
  there, `--port 0` disables TCP.
- `--db :memory:` runs purely in memory - no file, no restore, no snapshots
  (`KAGNI_DB` overrides the default snapshot path).
- `--no-save` loads an existing snapshot at boot but never writes back
  (redis `save ""`); a missing file is not created.

## Services and daemon mode

`--daemon` detaches kagni into the background (POSIX): the command prints
the child pid and returns. Logs go to `--logfile` (or nowhere);
`--pidfile PATH` writes the process id and removes it on graceful shutdown.
`SIGTERM` shuts the server down gracefully, final snapshot included -
useful for service managers.

```
kagni --daemon --pidfile /var/run/kagni.pid --logfile /var/log/kagni.log \
      --host 127.0.0.1 --db /var/lib/kagni/kagni.sqlite
```

Use absolute paths for `--db` / `--logfile` / `--pidfile` in daemon mode.

### systemd (or any foreground service manager)

Run kagni in the foreground and let the manager own it - SIGTERM then
triggers the graceful shutdown with its final snapshot:

```
[Service]
Type=simple
ExecStart=/usr/local/bin/kagni --host 127.0.0.1 \
    --db /var/lib/kagni/kagni.sqlite
Restart=on-failure
```

supervisord etc. work the same way: one foreground command, no `--daemon`.

## Storage

- Everything lives in memory with lazy key expiry (`EXPIRE`/`TTL`), and
  hashes add redis 7.4-style per-field expiries (`HEXPIRE` and friends).
  The sqlite snapshot is a full-table transaction, replaced every
  `--dump-interval` seconds and restored at boot. Expiries are persisted
  with each value (as absolute wall-clock deadlines) and re-armed on
  restore; keys whose deadline passed while the server was down are
  dropped, like redis.
- Strings are byte strings with redis semantics (counters are strings
  too). Lists are deques, giving O(1) push/pop at both ends. Bitmaps are
  roaring bitmaps, so sparse high-offset data stays compact where a
  redis-style byte string would grow linearly. Sorted sets are
  member→score dicts over a `bisect`-kept `(score, member)` list: rank
  queries are O(log n), writes shift the list in C, and score ties break
  on member bytes like redis.

## Commands

All 153 supported commands, exhaustive, grouped by data type:

| String | List | Set | Hash | Bitmap | Sorted set | Pub/Sub | Keys / admin |
| --- | --- | --- | --- | --- | --- | --- | --- |
| SET (NX/XX/GET/EX/PX/EXAT/PXAT/KEEPTTL)<br>GET<br>GETSET<br>GETDEL<br>GETEX<br>SETNX<br>SETEX<br>PSETEX<br>MSET<br>MSETNX<br>MGET<br>APPEND<br>STRLEN<br>GETRANGE<br>SETRANGE<br>INCR<br>INCRBY<br>INCRBYFLOAT<br>DECR<br>DECRBY<br>SUBSTR<br>LCS | LPUSH<br>RPUSH<br>LPUSHX<br>RPUSHX<br>LLEN<br>LINDEX<br>LSET<br>LRANGE<br>LTRIM<br>LREM<br>LINSERT<br>LPOP<br>RPOP<br>LMOVE<br>RPOPLPUSH<br>LPOS<br>LMPOP | SADD<br>SCARD<br>SMEMBERS<br>SISMEMBER<br>SMISMEMBER<br>SREM<br>SPOP<br>SRANDMEMBER<br>SMOVE<br>SDIFF<br>SDIFFSTORE<br>SINTER<br>SINTERCARD<br>SINTERSTORE<br>SUNION<br>SUNIONSTORE<br>SSCAN | HSET (variadic)<br>HGET<br>HMGET<br>HEXISTS<br>HDEL<br>HLEN<br>HKEYS<br>HVALS<br>HGETALL<br>HSTRLEN<br>HINCRBY<br>HINCRBYFLOAT<br>HRANDFIELD<br>HMSET<br>HSETNX<br>HSCAN<br>HEXPIRE/HPEXPIRE/HEXPIREAT/HPEXPIREAT<br>HTTL/HPTTL/HPERSIST/HEXPIRETIME/HPEXPIRETIME | SETBIT<br>GETBIT<br>BITCOUNT<br>BITPOS<br>BITOP<br>BITFIELD/BITFIELD_RO | ZADD (NX/XX/GT/LT/CH/INCR)<br>ZCARD<br>ZSCORE<br>ZMSCORE<br>ZINCRBY<br>ZRANK/ZREVRANK (WITHSCORE)<br>ZRANGE (BYSCORE/BYLEX/REV/LIMIT/WITHSCORES)<br>ZREVRANGE<br>ZRANGEBYSCORE<br>ZREVRANGEBYSCORE<br>ZRANGEBYLEX<br>ZREVRANGEBYLEX<br>ZCOUNT<br>ZLEXCOUNT<br>ZREM<br>ZREMRANGEBYRANK<br>ZREMRANGEBYSCORE<br>ZREMRANGEBYLEX<br>ZPOPMIN/ZPOPMAX<br>ZRANDMEMBER<br>ZSCAN<br>ZUNION/ZINTER/ZDIFF<br>ZUNIONSTORE/ZINTERSTORE/ZDIFFSTORE | SUBSCRIBE<br>UNSUBSCRIBE<br>PSUBSCRIBE<br>PUNSUBSCRIBE<br>PUBLISH<br>PUBSUB (CHANNELS/NUMSUB/NUMPAT) | PING<br>ECHO<br>HELLO (RESP2)<br>COMMAND<br>CONFIG (GET + SET notify-keyspace-events)<br>CLIENT<br>INFO<br>TYPE<br>DEL<br>EXPIRE<br>PEXPIRE<br>EXPIREAT<br>PEXPIREAT<br>EXPIRETIME<br>PEXPIRETIME<br>PERSIST<br>TTL<br>PTTL<br>KEYS<br>SCAN<br>EXISTS<br>TOUCH<br>DBSIZE<br>WATCH/UNWATCH<br>MULTI<br>EXEC<br>DISCARD<br>FLUSHDB<br>FLUSHALL |

Not implemented: blocking commands (`BLPOP`/`BRPOP`/`BLMOVE`/`BRPOPLPUSH`/
`BLMPOP`), streams and sharded pub/sub (`SPUBLISH`).

Beyond the table:

- Plain pub/sub (SUBSCRIBE/PSUBSCRIBE/PUBLISH) is supported - ephemeral,
  in-memory fan-out with redis' RESP2 semantics, including the
  subscribed-mode command gate and slow-subscriber disconnects. The
  sqlite snapshots never contain pub/sub state.
- Keyspace notifications work like redis: `CONFIG SET notify-keyspace-events`
  toggles the `__keyspace@0__:*` / `__keyevent@0__:*` channels (event
  names and class gating match redis, including lazy `expired` events).
- `WATCH`/`UNWATCH` implement optimistic transactions: `EXEC` aborts with
  a null array when a watched key changed, expired or got a new TTL.

## Testing

The suite mirrors redis 7.4 semantics per command - happy paths, error
matrices and wire shapes - plus an end-to-end battery over real sockets on
both event loops, redis-py driving a live server, a 63-command byte-parity
differential, and a multi-connection differential (pub/sub fan-out,
keyspace notifications, WATCH aborts) against a real redis. The GitHub
Actions workflow runs the suite on Python 3.11-3.13, feeds both RESP
parsers random bytes (`tests/test_fuzz.py`: only a clean `ProtocolError`,
never a crash) and hosts a `redis:7.4` service container for the
differential batteries.

kagni speaks RESP2: redis-py asyncio clients default to RESP3 - pass
`protocol=2` when connecting (sync clients default to RESP2).

### Integration tests: subprocess fixture

For tests that need a live endpoint, `kagni.testing` provides a
session-scoped pytest fixture that boots a real server in a subprocess on
an ephemeral port (in-memory, nothing on disk) and tears it down
afterwards. A subprocess keeps the test process's own event loop free, so
blocking redis-py calls work from sync tests:

```
# tests/conftest.py
pytest_plugins = ["kagni.testing"]

def test_cache(kagni_server):
    r = redis.Redis(host=kagni_server.host, port=kagni_server.port)
    assert r.set("k", "v") and r.get("k") == b"v"
```

`kagni.testing.start_server()` is the fixture-free version, for your own
fixture scopes.

### In-process embedding

Instead of a subprocess, `kagni.embed.serve()` runs the server inside the
caller's own event loop - asyncio or trio, detected from the running
context (`loop="auto"`, or force one with `loop="asyncio"`/`"trio"`). It
binds an ephemeral port and stops cleanly when the block exits: listeners
and active connections closed, snapshot dumper cancelled, final snapshot
written when a snapshot file is configured.

Asyncio app:

```python
import asyncio

import redis.asyncio as aredis

import kagni.embed

async def main():
    async with kagni.embed.serve() as server:
        r = aredis.Redis(host=server.host, port=server.port, protocol=2)
        await r.set("cache:frontpage", "v1")
        assert await r.get("cache:frontpage") == b"v1"
        await r.aclose()

asyncio.run(main())
```

Trio app - the same call serves on the running trio loop:

```python
import trio

import kagni.embed

async def main():
    async with kagni.embed.serve() as server:
        # server.host / server.port / server.url describe the endpoint;
        # talk RESP with trio.open_tcp_stream(server.host, server.port)
        # or drive any blocking redis client from a worker thread
        ...

trio.run(main)
```

With a snapshot file, state survives restarts (the exit dump persists it):

```python
async with kagni.embed.serve(db_path="dev.sqlite") as server:
    ...  # next serve() on the same file restores the keys
```

Your own async pytest fixture - a fresh in-memory store per test:

```python
import pytest
import redis.asyncio as aredis

import kagni.embed

@pytest.fixture
async def kagni():
    async with kagni.embed.serve() as server:
        yield aredis.Redis(host=server.host, port=server.port, protocol=2)

@pytest.mark.asyncio
async def test_counter(kagni):
    assert await kagni.incr("hits") == 1
```

(Async tests need an asyncio/trio pytest plugin such as pytest-asyncio or
anyio. For sync tests the subprocess fixture above is the right tool - its
server has its own loop, so blocking redis-py calls cannot deadlock.)

### Known gaps

- **The differential batteries need a real redis binary**, so they only
  run in the CI job that hosts one; by hand:
  `KAGNI_DIFF_REDIS=host:port python tests/differential.py` (single
  connection) and `tests/differential_multi.py` (multi-connection).
- **The 512 MB string-size guards are not exercised** (allocating that
  much in tests is not worth it); the guards are trivial bounds checks.
- **`INCRBYFLOAT` runs on double precision** - redis uses 80-bit long
  doubles and prints fixed-point; kagni prints the shortest round-trip
  repr, so results agree for everyday decimals (`10.5`, `0.1+0.2`) but
  may differ at extreme magnitudes.
- **Streams and the blocking commands are not implemented** (see the
  command table), so they have no tests.
