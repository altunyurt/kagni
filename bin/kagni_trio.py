# /usr/bin/env python

import trio
import logging
from collections import deque
from kagni.commands import COMMANDS
from kagni.db import db
from kagni.parser import protocolParser

log = logging.getLogger()
log.setLevel(logging.DEBUG)
log.addHandler(logging.StreamHandler())


async def protocolHandler(stream):
    response = deque()

    try:
        while True:
            data = await stream.receive_some(65535)
            if not data:
                return

            req = protocolParser(data)

            cmd_text = req[0].upper()
            command = COMMANDS.get(cmd_text)
            if not command:
                resp = f"-Unknown command {cmd_text} possible commands are {COMMANDS.keys()}\r\n".encode()
            else:
                resp = command(*req[1:])
            response.append(resp)
            await stream.send_all(b"".join(response))
            response.clear()
    except trio.BrokenResourceError:
        pass
    finally:
        response.clear()
        return


# dump database periodically
async def dumper():
    while True:
        db.dump()
        await trio.sleep(10)  # secs


async def main(hostname="localhost", port=6380):
    print("Listening on port {}".format(port))

    try:

        await trio.serve_tcp(protocolHandler, port, host=hostname)
    except KeyboardInterrupt:
        print("User requested shutdown.")
    finally:
        print("Redis is now ready to exit.")
    return 0


if __name__ == "__main__":
    trio.run(main)

# vim: set filetype=python
