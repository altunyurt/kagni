from enum import Enum
from enum import auto

SYM_CRLF = b"\r\n"


class Response(Enum):
    OK = auto()
    QUEUED = auto()
    PONG = auto()
    COMMAND = auto()
    NIL = auto()
    NIL_ARRAY = auto()  # RESP null array (*-1), distinct from an empty array


class Error(Exception):
    def __init__(self, class_, msg=""):
        self.class_ = class_
        self.message = msg


class Errors:
    """Pre-built RESP errors shared by the command implementations."""

    INVALID_CURSOR = Error("ERR", "invalid cursor")
    NOT_INT = Error("ERR", "value is not an integer or out of range")
    WRONGTYPE = Error(
        "WRONGTYPE", "Operation against a key holding the wrong kind of value"
    )
    SYNTAX = Error("ERR", "syntax error")
    NOKEY = Error("ERR", "no such key")
    INDEX_RANGE = Error("ERR", "index out of range")
    BIT_OFFSET = Error("ERR", "bit offset is not an integer or out of range")
    BIT_VALUE = Error("ERR", "bit is not an integer or out of range")
    BIT_ARG = Error("ERR", "The bit argument must be 1 or 0.")
    RANGE_OFFSET = Error("ERR", "offset is out of range")
    NOT_POSITIVE = Error("ERR", "value is out of range, must be positive")
    OVERFLOW = Error("ERR", "increment or decrement would overflow")
    STRING_OVERFLOW = Error(
        "ERR", "string exceeds maximum allowed size (proto-max-bulk-len)"
    )

    @staticmethod
    def arity(command):
        return Error("ERR", "wrong number of arguments for '{}' command".format(command))
