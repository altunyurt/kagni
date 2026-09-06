# kagni

Kagni is a Python-native, Redis-protocol data store daemon: everything in memory, snapshots to sqlite, one `pip install` away. Named after the Turkish ox-cart (kağnı) — not built for raw speed, but it gets things done.

## Why kagni

It is a real RESP server that lives comfortably inside Python workflows:

- **Testing / CI** — a genuine Redis-compatible endpoint over TCP or a unix
  socket for integration tests: real wire protocol, real pipelining, real
  persistence modes, no containers and no native builds. For component
  tests the command layer is importable directly, no sockets needed.
  (Alternatives like fakeredis run in-process only and speak no sockets.)
- **Embedded / sidecar** — the same venv that runs your Python service can
  run kagni next to it: `--db :memory:` for a pure-RAM cache, a sqlite
  snapshot file for durability, or `--no-save` to serve a seed dataset
  without ever writing back.
- **Native Python** — `pip install .` then `kagni` or `python -m kagni`;
  pick the event loop (asyncio+uvloop or trio); sqlite snapshots are
  inspectable with standard tooling.

It is not a Redis replacement where throughput or feature breadth matter:
expect a modest single-process op rate, a ~116-command subset, and no
blocking commands, replication, transactions or pub/sub.

## Running

Requires Python 3.11+ (developed on 3.13).

    uv sync                    # install deps and the `kagni` console script
    uv run kagni --help        # or: uv run python -m kagni
    pip install .              # plain-pip alternative; then: kagni --help

    kagni --loop asyncio|trio [--host HOST] [--port PORT] [--socket PATH]
          [--db PATH] [--dump-interval SECS] [--no-save] [--no-uvloop]
          [--daemon] [--pidfile PATH] [--logfile PATH]

Defaults: `asyncio` loop (uvloop when installed), `localhost:6379` (redis'
port; pass `--port` to run alongside a real redis), sqlite file
`kagni.sqlite`, snapshot every 20 s.

- TCP and a unix domain socket are additive: `--socket PATH` also listens there, `--port 0` disables TCP.
- `--db :memory:` runs purely in memory — no file, no restore, no snapshots.
- `--no-save` loads an existing snapshot at boot but never writes back (redis `save ""`); a missing file is not created.

## Services and daemon mode

`--daemon` detaches kagni into the background (POSIX): the command prints
the child pid and returns. Logs go to `--logfile` (or nowhere);
`--pidfile PATH` writes the process id and removes it on graceful
shutdown. `SIGTERM` shuts the server down gracefully, final snapshot
included — useful for service managers.

    kagni --daemon --pidfile /var/run/kagni.pid --logfile /var/log/kagni.log \
          --host 127.0.0.1 --db /var/lib/kagni/kagni.sqlite

Use absolute paths for `--db`/`--logfile`/`--pidfile` in daemon mode.

### systemd

systemd manages the daemonizing itself, so run kagni in the foreground
(no `--daemon`) and let the journal capture the logs:

    # /etc/systemd/system/kagni.service
    [Unit]
    Description=Kagni redis-like data store
    After=network.target

    [Service]
    Type=simple
    User=kagni
    ExecStart=/usr/local/bin/kagni --host 127.0.0.1 \
        --db /var/lib/kagni/kagni.sqlite
    Restart=on-failure

    [Install]
    WantedBy=multi-user.target

    systemctl daemon-reload
    systemctl enable --now kagni

### supervisord

Supervisord also expects foreground processes:

    # /etc/supervisor/conf.d/kagni.conf
    [program:kagni]
    command=/usr/local/bin/kagni --host 127.0.0.1 --db /var/lib/kagni/kagni.sqlite
    user=kagni
    autostart=true
    autorestart=true
    redirect_stderr=true
    stdout_logfile=/var/log/kagni.log

## Storage

- Everything lives in memory with lazy key expiry (`EXPIRE`/`TTL`); the sqlite snapshot is a full-table transaction, replaced every `--dump-interval` seconds and restored at boot. Expiries are persisted with each value (as absolute wall-clock deadlines) and re-armed on restore; keys whose deadline passed while the server was down are dropped, like redis.
- Strings are byte strings with redis semantics (counters are strings too). Lists are deques, giving O(1) push/pop at both ends. Bitmaps are roaring bitmaps, so sparse high-offset data stays compact where a redis-style byte string would grow linearly. Sorted sets are member→score dicts over a `bisect`-kept `(score, member)` list: rank queries are O(log n), writes shift the list in C, and score ties break on member bytes like redis.

## Commands

Supported commands, grouped by data type:

| String | List | Set | Hash | Bitmap | Sorted set | Keys / admin |
| --- | --- | --- | --- | --- | --- | --- |
| SET (NX/XX/GET/EX/PX/EXAT/PXAT/KEEPTTL)<br>GET<br>GETSET<br>GETDEL<br>GETEX<br>SETNX<br>SETEX<br>PSETEX<br>MSET<br>MSETNX<br>MGET<br>APPEND<br>STRLEN<br>GETRANGE<br>SETRANGE<br>INCR<br>INCRBY<br>INCRBYFLOAT<br>DECR<br>DECRBY<br>ECHO | LPUSH<br>RPUSH<br>LPUSHX<br>RPUSHX<br>LLEN<br>LINDEX<br>LSET<br>LRANGE<br>LTRIM<br>LREM<br>LINSERT<br>LPOP<br>RPOP<br>LMOVE<br>RPOPLPUSH<br>LPOS<br>LMPOP | SADD<br>SCARD<br>SMEMBERS<br>SISMEMBER<br>SREM<br>SPOP<br>SRANDMEMBER<br>SMOVE<br>SDIFF<br>SDIFFSTORE<br>SINTER<br>SINTERSTORE<br>SUNION<br>SUNIONSTORE | HSET (variadic)<br>HGET<br>HMGET<br>HEXISTS<br>HDEL<br>HLEN<br>HKEYS<br>HVALS<br>HGETALL<br>HINCRBY | SETBIT<br>GETBIT<br>BITCOUNT<br>BITPOS<br>BITOP | ZADD (NX/XX/GT/LT/CH/INCR)<br>ZCARD<br>ZSCORE<br>ZMSCORE<br>ZINCRBY<br>ZRANK/ZREVRANK (WITHSCORE)<br>ZRANGE (BYSCORE/BYLEX/REV/LIMIT/WITHSCORES)<br>ZREVRANGE<br>ZRANGEBYSCORE<br>ZREVRANGEBYSCORE<br>ZRANGEBYLEX<br>ZREVRANGEBYLEX<br>ZCOUNT<br>ZLEXCOUNT<br>ZREM<br>ZREMRANGEBYRANK<br>ZREMRANGEBYSCORE<br>ZREMRANGEBYLEX<br>ZPOPMIN/ZPOPMAX<br>ZRANDMEMBER<br>ZUNION/ZINTER/ZDIFF<br>ZUNIONSTORE/ZINTERSTORE/ZDIFFSTORE | PING<br>COMMAND<br>CONFIG<br>CLIENT<br>INFO<br>TYPE<br>DEL<br>EXPIRE<br>PEXPIRE<br>EXPIREAT<br>PEXPIREAT<br>PERSIST<br>TTL<br>PTTL<br>KEYS<br>SCAN<br>EXISTS<br>TOUCH<br>DBSIZE<br>MULTI<br>EXEC<br>DISCARD<br>FLUSHDB<br>FLUSHALL |

Not implemented (yet): blocking commands (`BLPOP`/`BRPOP`/`BLMOVE`), streams,
pub/sub, `WATCH` (`MULTI`/`EXEC`/`DISCARD` are supported) and `ZSCAN`
(consistently with `HSCAN`/`SSCAN`).

## Testing & known gaps

The test suite mirrors redis 7.4 semantics per command (happy paths, error
matrices, wire shapes) plus an end-to-end battery over real sockets on
both event loops and both listener types.  Redis 7.4 is the compatibility
target (the LTS line; the implemented subset behaves identically in 8.x).
The GitHub Actions workflow runs the suite on Python 3.11-3.13, feeds
both RESP parsers random bytes (`tests/test_fuzz.py`: only a clean
`ProtocolError`, never a crash), and runs `tests/differential.py` - a
~400-command byte-parity battery - against a real `redis:7.4` service
container.  Known gaps, intentionally left
open:

### Integration tests without a redis

For tests that need a live endpoint, `kagni.testing` provides a
session-scoped pytest fixture that boots a real server on an ephemeral
port (in-memory, nothing on disk) and tears it down afterwards:

    # tests/conftest.py
    pytest_plugins = ["kagni.testing"]

    def test_cache(kagni_server):
        r = redis.Redis(host=kagni_server.host, port=kagni_server.port)
        assert r.set("k", "v") and r.get("k") == b"v"

`kagni.testing.start_server()` is the fixture-free version (use it as a
context manager for your own function-scoped fixtures).

- **The differential battery needs a redis binary**, so it only runs in
  the CI job that hosts one; by hand:
  `KAGNI_DIFF_REDIS=host:port python tests/differential.py`.
- **The 512 MB string-size guards are not exercised** (allocating that
  much in tests is not worth it); the guards are trivial bounds checks.
- **`INCRBYFLOAT` runs on double precision** — redis uses 80-bit long
  doubles and prints fixed-point; kagni prints the shortest round-trip
  repr, so results agree for everyday decimals (`10.5`, `0.1+0.2`) but
  may differ at extreme magnitudes (exponents, sub-1e-16 deltas).
- **Interpreter coverage (3.11–3.13) is verified ad hoc**, not
  reproducible in CI; the declared floor is 3.11.
- **`WATCH`, pub/sub, blocking commands, sorted sets and streams are not
  implemented** (see the command table), so they have no tests.
