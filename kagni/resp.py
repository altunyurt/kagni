from .constants import SYM_CRLF
from .constants import Error
from .constants import Response


__all__ = ["protocolBuilder", "protocolParser"]


responses_dict = {
   Response.OK: [b"+OK"],
   Response.NIL: [b"$-1"],
   Response.QUEUED: [b"+QUEUED"],
   Response.PONG: [b"+PONG"],
   Response.COMMAND: [b"+COMMAND"],
}

# https://github.com/chekart/rediserver
def _resp_dumps(value):

    if isinstance(value, bytes):
        return [f"${len(value)}".encode(), value]

    if isinstance(value, int):
        return [f":{value}".encode()]

    if isinstance(value, (list, tuple)):
        result = [f"*{len(value)}".encode()]
        for item in value:
            result.extend(_resp_dumps(item))
        return result

    if value in responses_dict:
        return responses_dict[value]

    if isinstance(value, Error):
        return [f"-{value.class_}".encode() + f" {value.message}".encode()]

    raise NotImplementedError()


def protocolBuilder(value):
    response = _resp_dumps(value)
    response = SYM_CRLF.join(response) + SYM_CRLF
    return response


class RESP:
    def __init__(self, data):
        self.data = data.split(b"\r\n")[:-1]
        self.pos = 0
        self.len = len(self.data)

    def __iter__(self):
        return self

    def __next__(self):
        if self.pos >= self.len:
            raise StopIteration()
        data = self.data[self.pos]
        self.pos += 1
        return data


def parse(payload):
    # payload.0 = "$2"

    _data = next(payload)
    _type = chr(_data[0])

    # TODO: type and length check according to protocol defs
    if _type == "*":
        l = int(_data[1:], 10)  # *3 -> 3
        return [parse(payload) for i in range(l)]

    if _type == ":":
        return int(_data[1:], 10)

    if _type == "$":
        return next(payload)

    return _data


def protocolParser(_data):
    resp = RESP(_data)
    return parse(resp)
