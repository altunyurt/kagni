from enum import Enum
from enum import auto

SYM_CRLF = b"\r\n"


class Response(Enum):
    OK = auto()
    QUEUED = auto()
    PONG = auto()
    NIL = auto()
    NIL_ARRAY = auto()  # RESP null array (*-1), distinct from an empty array


class SimpleString:
    """A RESP simple-string reply ("+..."), for results like TYPE's
    "none"/"string"/"list" that are not part of the fixed Response set."""

    def __init__(self, value: str):
        self.value = value


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
    RANK_ZERO = Error(
        "ERR",
        "RANK can't be zero: use 1 to start from the first match, 2 from "
        "the second ... or use negative to start from the end of the list",
    )
    COUNT_NEG = Error("ERR", "COUNT can't be negative")
    MAXLEN_NEG = Error("ERR", "MAXLEN can't be negative")
    NOT_FLOAT = Error("ERR", "value is not a valid float")
    FLOAT_OVERFLOW = Error("ERR", "increment would produce NaN or Infinity")
    BIT_OFFSET = Error("ERR", "bit offset is not an integer or out of range")
    BIT_VALUE = Error("ERR", "bit is not an integer or out of range")
    BIT_ARG = Error("ERR", "The bit argument must be 1 or 0.")
    RANGE_OFFSET = Error("ERR", "offset is out of range")
    NOT_POSITIVE = Error("ERR", "value is out of range, must be positive")
    OVERFLOW = Error("ERR", "increment or decrement would overflow")
    STRING_OVERFLOW = Error(
        "ERR", "string exceeds maximum allowed size (proto-max-bulk-len)"
    )
    # sorted-set errors (messages mirror redis 7.4)
    MIN_MAX_FLOAT = Error("ERR", "min or max is not a float")
    LEX_RANGE = Error("ERR", "min or max not valid string range item")
    NAN_RESULT = Error("ERR", "resulting score is not a number (NaN)")
    ZADD_CONFLICT = Error(
        "ERR", "GT, LT, and/or NX options at the same time are not compatible"
    )
    ZADD_XX_NX = Error(
        "ERR", "XX and NX options at the same time are not compatible"
    )
    ZADD_INCR_PAIR = Error(
        "ERR", "INCR option supports a single increment-element pair"
    )
    LIMIT_NEEDS_BY = Error(
        "ERR",
        "syntax error, LIMIT is only supported in combination with either "
        "BYSCORE or BYLEX",
    )
    WITHSCORES_BYLEX = Error(
        "ERR", "syntax error, WITHSCORES not supported in combination with BYLEX"
    )
    WEIGHT_FLOAT = Error("ERR", "weight value is not a float")
    # hash counter errors
    HASH_NOT_INT = Error("ERR", "hash value is not an integer")

    @staticmethod
    def arity(command):
        return Error("ERR", "wrong number of arguments for '{}' command".format(command))

    @staticmethod
    def no_keys(command):
        return Error(
            "ERR", "at least 1 input key is needed for '{}' command".format(command)
        )
