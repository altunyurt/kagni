# /usr/bin/env python

import trio
import logging
from collections import deque
from functools import partial
from kagni.commands import Commands
from kagni.data import Data
from kagni.db import DB
from kagni.resp import protocolParser

log = logging.getLogger()
log.setLevel(logging.DEBUG)
log.addHandler(logging.StreamHandler())


async def protocolHandler(stream, command_handler=None):
    response = deque()

    try:
        while True:
            data = await stream.receive_some(65535)
            if not data:
                return

            req = protocolParser(data)

            cmd_text = req[0].upper()
            command = getattr(command_handler, cmd_text.decode())  # command name in bytes
            if not command:
                resp = f"-Unknown command {cmd_text} \r\n".encode()
            else:
                resp = command(*req[1:])
            response.append(resp)
            await stream.send_all(b"".join(response))
            response.clear()
    except trio.BrokenResourceError:
        import traceback

        print(traceback.format_exc())
    except:
        import traceback

        print(traceback.format_exc())

    finally:
        response.clear()
        return

from time import sleep 

# dump database periodically
async def dumper(db, data):
    while True:
        db.dump(data)
        # await trio.sleep(2000)  # secs
        sleep(20)
        # async trio sqlite gerekiyor 

        print("yea")


async def main(hostname="localhost", port=6380):
    print("Listening on port {}".format(port))

    try:
        data = Data()
        db = DB('./deneme.sqlite')
        c_handler = Commands(data)
        server = partial(
            trio.serve_tcp,
            partial(protocolHandler, command_handler=c_handler),
            port=port,
            host=hostname,
        )
        async with trio.open_nursery() as nursery:
            # nursery.start_soon(dumper, db, data)
            nursery.start_soon(server)
    except KeyboardInterrupt:
        print("User requested shutdown.")
    finally:
        print("Redis is now ready to exit.")
    return 0


if __name__ == "__main__":
    trio.run(main)
# vim: set filetype=python
