from enum import Enum
from enum import auto

SYM_CRLF = b"\r\n"


class Response(Enum):
    OK = auto()
    QUEUED = auto()
    PONG = auto()
    COMMAND = auto()
    NIL = auto()


class Error(Exception):
    def __init__(self, class_, msg=""):
        self.class_ = class_
        self.message = msg


class Errors:
    INVALID_CURSOR = Error("ERR", "invalid cursor")
    NOT_INT = Error("ERR", "value is not an integer or out of range")
    WRONGTYPE = Error(
        "WRONGTYPE", "Operation against a key holding the wrong kind of value"
    )
