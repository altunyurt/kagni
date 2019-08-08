import hiredis

reader = hiredis.Reader()

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


def protocolParser(_data):
    reader.feed(_data)
    return reader.gets()
