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
expect a modest single-process op rate, a ~65-command subset, and no
blocking commands, replication, transactions or pub/sub.

## Running

Requires Python 3.10+ (developed on 3.13).

    uv sync                    # install deps and the `kagni` console script
    uv run kagni --help        # or: uv run python -m kagni
    pip install .              # plain-pip alternative; then: kagni --help

    kagni --loop asyncio|trio [--host HOST] [--port PORT] [--socket PATH]
          [--db PATH] [--dump-interval SECS] [--no-save] [--no-uvloop]
          [--daemon] [--pidfile PATH] [--logfile PATH]

Defaults: `asyncio` loop (uvloop when installed), `localhost:6380`, sqlite file `kagni.sqlite`, snapshot every 20 s.

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
          --host 127.0.0.1 --port 6380 --db /var/lib/kagni/kagni.sqlite

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
    ExecStart=/usr/local/bin/kagni --host 127.0.0.1 --port 6380 \
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
    command=/usr/local/bin/kagni --host 127.0.0.1 --port 6380 --db /var/lib/kagni/kagni.sqlite
    user=kagni
    autostart=true
    autorestart=true
    redirect_stderr=true
    stdout_logfile=/var/log/kagni.log

## Storage

- Everything lives in memory with lazy key expiry (`EXPIRE`/`TTL`); the sqlite snapshot is a full-table transaction, replaced every `--dump-interval` seconds and restored at boot.
- Strings are byte strings with redis semantics (counters are strings too). Lists are deques, giving O(1) push/pop at both ends. Bitmaps are roaring bitmaps, so sparse high-offset data stays compact where a redis-style byte string would grow linearly.

## Commands

Supported commands, grouped by data type:

| String | List | Set | Hash | Bitmap | Keys / admin |
| --- | --- | --- | --- | --- | --- |
| SET<br>GET<br>GETSET<br>MSET<br>MGET<br>APPEND<br>STRLEN<br>GETRANGE<br>SETRANGE<br>INCR<br>INCRBY<br>DECR<br>DECRBY | LPUSH<br>RPUSH<br>LPUSHX<br>RPUSHX<br>LLEN<br>LINDEX<br>LSET<br>LRANGE<br>LTRIM<br>LREM<br>LINSERT<br>LPOP<br>RPOP<br>LMOVE<br>RPOPLPUSH<br>LPOS<br>LMPOP | SADD<br>SCARD<br>SMEMBERS<br>SISMEMBER<br>SREM<br>SPOP<br>SRANDMEMBER<br>SMOVE<br>SDIFF<br>SDIFFSTORE<br>SINTER<br>SINTERSTORE<br>SUNION<br>SUNIONSTORE | HSET<br>HGET<br>HEXISTS<br>HDEL<br>HGETALL | SETBIT<br>GETBIT<br>BITCOUNT<br>BITPOS<br>BITOP | PING<br>COMMAND<br>CONFIG<br>TYPE<br>DEL<br>EXPIRE<br>PERSIST<br>TTL<br>KEYS<br>FLUSHDB<br>FLUSHALL |

Not implemented (yet): blocking commands (`BLPOP`/`BRPOP`/`BLMOVE`), sorted sets, streams, pub/sub, transactions, `SCAN`, and command variants like `SET NX/EX` or `GETEX`.
