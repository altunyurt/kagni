
SYM_CRLF = b"\r\n"
OK = object()
QUEUED = object()
PONG = object()
COMMAND = object()
NIL = None

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

