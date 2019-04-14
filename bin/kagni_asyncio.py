# /usr/bin/env python

import asyncio
import uvloop
import hiredis
import logging
from kagni.commands import COMMANDS
import collections

log = logging.getLogger()
log.setLevel(logging.DEBUG)
log.addHandler(logging.StreamHandler())



# her bağlantıda çağrılıyor bu
class RedisServerProtocol(asyncio.Protocol):
    def __init__(self):
        self.parser = hiredis.Reader()
        self.response = collections.deque()

    def connection_made(self, transport):
        self.transport = transport

    def data_received(self, data):
        self.parser.feed(data)

        while True:
            resp = b''
            req = self.parser.gets()

            # log.debug(f"DBG: {req}")
            if req is False:
                break

            cmd_text = req[0].upper()
            command = COMMANDS.get(cmd_text)
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
    coro = loop.create_server(RedisServerProtocol, hostname, port)
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

