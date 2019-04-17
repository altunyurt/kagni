from .constants import *

__all__ = ['protocolBuilder', 'protocolParser']


# https://github.com/chekart/rediserver
def _resp_dumps(value):
    if value is OK:
        return [b"+OK"]

    if value is NIL:
        return [b"$-1"]

    if value is QUEUED:
        return [b"+QUEUED"]

    if value is PONG:
        return [b"+PONG"]

    if value is COMMAND:
        return [b"+COMMAND"]

    if isinstance(value, int):
        return [b":" + f"{value}".encode()]

    if isinstance(value, str):
        value = value.encode()

    if isinstance(value, bytes):
        return [b"$" + f"{len(value)}".encode(), value]

    if isinstance(value, Error):
        return [b"-" + f"{value.class_}".encode() + b" " + f"{value.message}".encode()]

    if isinstance(value, (list, tuple)):
        result = [b"*" + f"{len(value)}".encode()]
        for item in value:
            result.extend(_resp_dumps(item))
        return result

    raise NotImplementedError()


def protocolBuilder(value):
    response = _resp_dumps(value)
    response = SYM_CRLF.join(response) + SYM_CRLF
    return response


class RESP:
    def __init__(self, data):
        self.data = data.split(b"\r\n")
        self.pos = 0
        self.len = len(self.data)

    def __iter__(self):
        return self

    def __next__(self):
        if self.pos >= self.len - 1:
            raise StopIteration()
        data = self.data[self.pos]
        self.pos += 1
        return data


def parse(payload):
    # payload.0 = "$2"

    _header = next(payload)
    _type = chr(_header[0])

    # TODO: type and length check according to protocol defs
    if _type == ":":
        return float(_header[1:])

    if _type == "$":
        return next(payload)

    if _type == "*":
        _l = int(_header[1:])
        return [parse(payload) for i in range(_l)]

    raise NotImplementedError(f"Unknown message type: {_type}")


def protocolParser(_data):
    resp = RESP(_data)
    return parse(resp)
