from .constants import SYM_CRLF
from .constants import Error
from .constants import Response

__all__ = ["protocolBuilder", "protocolParser", "RESPReader", "ProtocolError"]


responses_dict = {
   Response.OK: [b"+OK"],
   Response.NIL: [b"$-1"],
   Response.QUEUED: [b"+QUEUED"],
   Response.PONG: [b"+PONG"],
   Response.COMMAND: [b"+COMMAND"],
}


def _resp_dumps(value):
    if isinstance(value, bytes):
        return [b"$%d" % len(value), value]

    if isinstance(value, int):
        return [b":%d" % value]

    if isinstance(value, (list, tuple)):
        result = [b"*%d" % len(value)]
        for item in value:
            result.extend(_resp_dumps(item))
        return result

    if isinstance(value, Response):
        return responses_dict[value]

    if isinstance(value, Error):
        line = b"-" + value.class_.encode()
        if value.message:
            line += b" " + value.message.encode()
        return [line]

    raise NotImplementedError("cannot encode %r" % (value,))


def protocolBuilder(value):
    response = _resp_dumps(value)
    response = SYM_CRLF.join(response) + SYM_CRLF
    return response


class ProtocolError(Exception):
    """Malformed RESP payload.  The connection should receive a ``-ERR``
    line and be closed (matching redis behaviour on protocol errors)."""


def _read_line(buf, pos):
    """Return ``(line, next_pos)`` for the CRLF-terminated line starting at
    ``pos``, or ``(None, None)`` when the line is not complete yet."""
    end = buf.find(b"\r\n", pos)
    if end == -1:
        return None, None
    return bytes(buf[pos:end]), end + 2


def _parse_message(buf, pos):
    """Parse one RESP value at ``pos``.

    Returns ``(value, next_pos)``, ``None`` when more data is needed, and
    raises ``ProtocolError`` for malformed input.  Bulk payloads are framed
    with their declared ``$<len>`` so values may legally contain ``\r\n``.
    """
    if pos >= len(buf):
        return None
    marker = buf[pos]

    if marker == ord("*"):
        return _parse_array(buf, pos)

    if marker == ord("$"):
        return _parse_bulk(buf, pos)

    if marker == ord(":"):
        line, npos = _read_line(buf, pos + 1)
        if line is None:
            return None
        try:
            return int(line), npos
        except ValueError:
            raise ProtocolError("invalid integer")

    if marker in (ord("+"), ord("-")):
        line, npos = _read_line(buf, pos)
        if line is None:
            return None
        return line, npos

    # inline command, e.g. "PING\r\n" (redis also accepts those)
    line, npos = _read_line(buf, pos)
    if line is None:
        return None
    return [token for token in line.split(b" ") if token], npos


def _parse_array(buf, pos):
    line, npos = _read_line(buf, pos + 1)
    if line is None:
        return None
    try:
        count = int(line)
    except ValueError:
        raise ProtocolError("invalid multibulk length")
    if count == -1:
        return None, npos
    if count < -1:
        raise ProtocolError("invalid multibulk length")

    items = []
    for _ in range(count):
        parsed = _parse_message(buf, npos)
        if parsed is None:
            return None
        item, npos = parsed
        items.append(item)
    return items, npos


def _parse_bulk(buf, pos):
    line, npos = _read_line(buf, pos + 1)
    if line is None:
        return None
    try:
        length = int(line)
    except ValueError:
        raise ProtocolError("invalid bulk length")
    if length == -1:
        return None, npos
    if length < -1:
        raise ProtocolError("invalid bulk length")

    if len(buf) < npos + length + 2:
        return None  # incomplete: wait for the rest of the payload
    if bytes(buf[npos + length : npos + length + 2]) != SYM_CRLF:
        raise ProtocolError("bulk value is not CRLF terminated")
    return bytes(buf[npos : npos + length]), npos + length + 2


class RESPReader:
    """Incremental RESP parser.

    One instance per connection.  ``feed()`` accepts whatever the socket
    delivers (arbitrary fragment sizes, several pipelined commands per
    chunk) and returns every complete command/value that could be parsed
    out of it; partial frames are kept in the internal buffer until the
    rest arrives.  Raises ``ProtocolError`` on malformed input.
    """

    # mirrors redis proto-max-bulk-len: guards the buffer against a peer
    # that announces a giant payload and never delivers it
    MAX_BUFFER = 512 * 1024 * 1024

    def __init__(self):
        self._buffer = bytearray()

    def feed(self, data):
        self._buffer.extend(data)
        if len(self._buffer) > self.MAX_BUFFER:
            raise ProtocolError("request exceeds maximum allowed size")

        messages = []
        while True:
            parsed = _parse_message(self._buffer, 0)
            if parsed is None:
                break
            value, consumed = parsed
            del self._buffer[:consumed]
            messages.append(value)
        return messages


def protocolParser(_data):
    """Parse exactly one complete RESP message out of *data*.

    Convenience for tests and one-shot callers: *data* must contain a
    single, complete message (no partial frames, no trailing messages).
    """
    reader = RESPReader()
    messages = reader.feed(_data)
    if not messages:
        raise ProtocolError("incomplete RESP message")
    if len(messages) != 1:
        raise ProtocolError("trailing data after RESP message")
    return messages[0]
