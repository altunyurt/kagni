# /usr/bin/env python

import asyncio
import uvloop
import logging
from kagni.commands import Commands
from kagni.data import Data
from kagni.resp import protocolParser
import collections
from functools import partial

log = logging.getLogger()
log.setLevel(logging.DEBUG)
log.addHandler(logging.StreamHandler())


# her bağlantıda çağrılıyor bu
class RedisServerProtocol(asyncio.Protocol):
    def __init__(self, command_handler):
        self.response = collections.deque()
        self.c_handler = command_handler

    def connection_made(self, transport):
        self.transport = transport

    def data_received(self, data):

        resp = b""
        req = protocolParser(data)

        cmd_text = req[0].upper()
        command = getattr(self.c_handler, cmd_text.decode())
        if not command:
            resp = f"-Unknown command {cmd_text}\r\n".encode()
        else:
            resp = command(*req[1:])
        self.response.append(resp)

        self.transport.writelines(self.response)
        self.response.clear()


def main(hostname="localhost", port=6380):
    uvloop.install()
    loop = asyncio.get_event_loop()
    command_handler = Commands(data=Data())
    protocolHandler = partial(lambda *n: RedisServerProtocol(command_handler))
    coro = loop.create_server(protocolHandler, hostname, port)
    server = loop.run_until_complete(coro)
    print("Listening on port {}".format(port))
    try:
        loop.run_forever()
    except KeyboardInterrupt:
        print("User requested shutdown.")
    finally:
        server.close()
        loop.run_until_complete(server.wait_closed())
        loop.close()
        print("Redis is now ready to exit.")
    return 0


if __name__ == "__main__":
    main()

# vim: set syntax=python
