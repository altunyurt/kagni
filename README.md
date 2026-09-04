# kagni

Kagni is a Redis-like data store daemon. It speaks RESP over TCP or unix sockets, keeps everything in memory and snapshots it to sqlite. Named after the Turkish ox-cart (kağnı) — slow, but it gets things done.

## Running

Requires Python 3.13+.

    uv sync                    # install deps and the `kagni` console script
    uv run kagni --help        # or: uv run python -m kagni
    pip install .              # plain-pip alternative; then: kagni --help

    kagni --loop asyncio|trio [--host HOST] [--port PORT] [--socket PATH]
          [--db PATH] [--dump-interval SECS] [--no-save] [--no-uvloop]

Defaults: `asyncio` loop (uvloop when installed), `localhost:6380`, sqlite file `kagni.sqlite`, snapshot every 20 s.

- TCP and a unix domain socket are additive: `--socket PATH` also listens there, `--port 0` disables TCP.
- `--db :memory:` runs purely in memory — no file, no restore, no snapshots.
- `--no-save` loads an existing snapshot at boot but never writes back (redis `save ""`); a missing file is not created.

## Storage

- Everything lives in memory with lazy key expiry (`EXPIRE`/`TTL`); the sqlite snapshot is a full-table transaction, replaced every `--dump-interval` seconds and restored at boot.
- Strings are byte strings with redis semantics (counters are strings too). Lists are deques, giving O(1) push/pop at both ends. Bitmaps are roaring bitmaps, so sparse high-offset data stays compact where a redis-style byte string would grow linearly.

## Commands

Supported commands, grouped by data type:

| String | List | Set | Hash | Bitmap | Keys / admin |
| --- | --- | --- | --- | --- | --- |
| SET<br>GET<br>GETSET<br>MSET<br>MGET<br>APPEND<br>STRLEN<br>GETRANGE<br>SETRANGE<br>INCR<br>INCRBY<br>DECR<br>DECRBY | LPUSH<br>RPUSH<br>LPUSHX<br>RPUSHX<br>LLEN<br>LINDEX<br>LSET<br>LRANGE<br>LTRIM<br>LREM<br>LINSERT<br>LPOP<br>RPOP<br>LMOVE<br>RPOPLPUSH<br>LPOS<br>LMPOP | SADD<br>SCARD<br>SMEMBERS<br>SISMEMBER<br>SREM<br>SPOP<br>SRANDMEMBER<br>SMOVE<br>SDIFF<br>SDIFFSTORE<br>SINTER<br>SINTERSTORE<br>SUNION<br>SUNIONSTORE | HSET<br>HGET<br>HEXISTS<br>HDEL<br>HGETALL | SETBIT<br>GETBIT<br>BITCOUNT<br>BITPOS<br>BITOP | PING<br>COMMAND<br>CONFIG<br>TYPE<br>DEL<br>EXPIRE<br>PERSIST<br>TTL<br>KEYS<br>FLUSHDB<br>FLUSHALL |

Not implemented (yet): blocking commands (`BLPOP`/`BRPOP`/`BLMOVE`), sorted sets, streams, pub/sub, transactions, `SCAN`, and command variants like `SET NX/EX` or `GETEX`.
