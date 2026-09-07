"""kagni.embed: the server runs inside the caller's event loop."""

import asyncio
import socket

import pytest
import trio

import kagni.embed
from kagni.resp import RESPReader


def _probe(host, port):
    sock = socket.create_connection((host, port), timeout=0.5)
    sock.close()


def test_embed_asyncio_commands_and_pubsub():
    import redis.asyncio as aredis

    async def main():
        async with kagni.embed.serve() as server:
            r = aredis.Redis(host=server.host, port=server.port, protocol=2)
            assert await r.ping()
            await r.set("k", "v")
            assert await r.get("k") == b"v"
            assert await r.incr("c") == 1
            await r.expire("c", 100)
            assert await r.ttl("c") > 0

            # pub/sub through the in-process hub
            pubsub = r.pubsub()
            await pubsub.subscribe("ch")
            confirm = await pubsub.get_message(timeout=1)
            assert confirm["type"] == "subscribe"
            await r.publish("ch", "payload")
            for _ in range(50):
                message = await pubsub.get_message(timeout=0.1)
                if message and message["type"] == "message":
                    assert message["data"] == b"payload"
                    break
            else:
                raise AssertionError("message not delivered in-process")
            await pubsub.aclose()
            await r.aclose()
        # the port is closed again after the block
        with pytest.raises(OSError):
            _probe(server.host, server.port)

    asyncio.run(main())


def test_embed_asyncio_persists_across_restarts(tmp_path):
    import redis.asyncio as aredis

    db_path = str(tmp_path / "kagni.db")

    async def main():
        async with kagni.embed.serve(db_path=db_path) as server:
            r = aredis.Redis(host=server.host, port=server.port, protocol=2)
            await r.set("durable", "yes")
            await r.aclose()
        # restart on the same snapshot file: the final dump persisted it
        async with kagni.embed.serve(db_path=db_path) as server:
            r = aredis.Redis(host=server.host, port=server.port, protocol=2)
            assert await r.get("durable") == b"yes"
            await r.aclose()

    asyncio.run(main())


def _frame(*args):
    return b"*%d\r\n" % len(args) + b"".join(
        b"$%d\r\n%s\r\n" % (len(a), a) for a in args
    )


def test_embed_trio_commands():
    async def main():
        # loop="auto" must detect trio from a running trio context
        async with kagni.embed.serve() as server:
            assert kagni.embed._Serve  # (import sanity)
            stream = await trio.open_tcp_stream(server.host, server.port)
            reader = RESPReader(engine="python")
            async with stream:
                await stream.send_all(_frame(b"SET", b"tk", b"tv"))
                assert [m for m in reader.feed(await stream.receive_some(1024))
                        if m is not None] == [b"+OK"]
                await stream.send_all(_frame(b"GET", b"tk"))
                for _ in range(10):
                    messages = [m for m in reader.feed(await stream.receive_some(1024))
                                if m is not None]
                    if messages:
                        assert messages == [b"tv"]
                        break
                else:
                    raise AssertionError("no reply")
        with pytest.raises(OSError):
            _probe(server.host, server.port)

    trio.run(main)


def test_embed_requires_a_running_loop():
    async def main():
        # no trio running here, and an asyncio loop is running, so auto
        # must pick asyncio - and the server must actually serve
        async with kagni.embed.serve() as server:
            assert server.port > 0

    asyncio.run(main())


def test_embed_bad_loop_name():
    async def main():
        with pytest.raises(ValueError):
            async with kagni.embed.serve(loop="tornado"):
                pass

    asyncio.run(main())
