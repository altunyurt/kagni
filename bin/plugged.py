from functools import partial
from kagni.commands import Commands
from kagni.data import Data
from kagni.db import DB
from kagni.resp import protocolParser
from kagni.resp import protocolBuilder
from kagni.constants import Errors, Response
import logging
import traceback
import trio


log = logging.getLogger()
log.setLevel(logging.DEBUG)
log.addHandler(logging.StreamHandler())


b_upper = bytes.upper

data = Data()
db = DB('./deneme.sqlite')
c_handler = Commands(data)

def commandHandler(cmd, *args):
    command = getattr(c_handler,b_upper(cmd).decode())
    return command(*args)
   

async def requestHandler(stream):

    try:
        async for data in stream:
            # pipe da olabilir. Her zaman için list dönmeli
            request = protocolParser(data)
            response = commandHandler(*request)
            await stream.send_all(response)
    except:
        print(traceback.format_exc())

    return


async def server_task(send_channel, receive_channel):
    print(f"Listening on port 6380")

    return await trio.serve_tcp(requestHandler, port=6380, host="localhost")


async def main():

    async with trio.open_nursery() as nursery:
        send, recv = trio.open_memory_channel(0)
        # açık kanal bırakmamak gerekiyor; yoksa bekliyor
        async with send, recv:
            nursery.start_soon(server_task, send, recv)


if __name__ == "__main__":
    trio.run(main)
