from .constants import SYM_CRLF
from .constants import Error
from .constants import Response
from .constants import SimpleString

try:
    import hiredis  # optional C accelerator; falls back to the pure parser
except ImportError:
    hiredis = None

__all__ = ["protocolBuilder", "protocolParser", "RESPReader", "ProtocolError"]


responses_dict = {
   Response.OK: [b"+OK"],
   Response.NIL: [b"$-1"],
   Response.NIL_ARRAY: [b"*-1"],
   Response.QUEUED: [b"+QUEUED"],
   Response.PONG: [b"+PONG"],
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

    if isinstance(value, SimpleString):
        return [b"+" + value.value.encode()]

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


def _wire_length(message):
    """Exact wire size of a parsed message, or None when it cannot be
    re-encoded canonically (nulls/errors) — boundary tracking then stays
    disabled for the connection."""
    try:
        return len(protocolBuilder(message))
    except (NotImplementedError, TypeError):
        return None


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

    # inline command, e.g. "PING\r\n" (redis also accepts those); runs of
    # whitespace separate the tokens
    line, npos = _read_line(buf, pos)
    if line is None:
        return None
    return line.split(), npos


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


# bytes that start a RESP-framed message; anything else starts an inline
# command line ("PING\r\n", "SET key value\r\n")
_RESP_MARKERS = frozenset(b"*$:+-")


class RESPReader:
    """Incremental RESP parser — one instance per connection.

    ``feed()`` accepts whatever the socket delivers (arbitrary fragment
    sizes, several pipelined commands per chunk) and returns every complete
    command/value that could be parsed out of it; partial frames are kept
    internally until the rest arrives.  Raises ``ProtocolError`` on
    malformed input.

    Engines:
    - ``"hiredis"`` (default when hiredis is installed): C-speed parsing.
      hiredis itself rejects redis *inline* commands (``PING\r\n``), which
      redis-benchmark's PING_INLINE test and telnet users send, so this
      class parses inline command lines itself whenever the connection is
      at a message boundary (boundary tracking is exact for well-formed
      frames: fed vs. parsed byte counts).
    - ``"python"``: pure-python parser, always available.  It also applies
      a buffer cap (mirroring redis' proto-max-bulk-len) against a peer
      that announces a giant payload and never delivers it.

    Unlike the plugged branch experiment this replaces, the hiredis reader
    is per-connection state here, is never memoised, and every complete
    message in a chunk is drained (pipelining).
    """

    # mirrors redis proto-max-bulk-len: guards the pure parser's buffer
    # against a peer that announces a giant payload and never delivers it
    MAX_BUFFER = 512 * 1024 * 1024

    def __init__(self, engine=None):
        if engine is None:
            engine = "hiredis" if hiredis is not None else "python"
        if engine not in ("hiredis", "python"):
            raise ValueError("unknown engine %r" % engine)
        if engine == "hiredis" and hiredis is None:
            raise ValueError("hiredis engine requested but hiredis is not installed")
        self._engine = engine
        self._buffer = bytearray()
        self._reader = hiredis.Reader() if engine == "hiredis" else None
        # inline interception state (hiredis engine only): hiredis rejects
        # inline commands, so they are parsed here while the connection is
        # at a message boundary.  Once a RESP-framed message is handed to
        # hiredis it owns the stream until fed/consumed byte counts prove
        # it is back at a boundary (canonical RESP re-encoding length is
        # exact for well-formed client frames).
        self._engaged = False
        self._boundary_unknown = False
        self._fed = 0
        self._consumed = 0

    @property
    def engine(self):
        return self._engine

    def feed(self, data):
        if self._engine == "hiredis":
            return self._feed_hiredis(data)
        return self._feed_python(data)

    def _feed_hiredis(self, data):
        messages = []

        if not self._engaged and not self._boundary_unknown:
            # hiredis rejects redis *inline* commands ("PING\r\n", used by
            # redis-benchmark's PING_INLINE and telnet), so while the
            # connection is at a message boundary we parse inline command
            # lines ourselves and only hand RESP-framed data to hiredis.
            self._buffer.extend(data)
            if len(self._buffer) > self.MAX_BUFFER:
                raise ProtocolError("request exceeds maximum allowed size")

            while self._buffer:
                if self._buffer[0] in _RESP_MARKERS:
                    # a framed message starts here: hiredis owns the
                    # stream until it provably returns to a boundary
                    self._engaged = True
                    data = bytes(self._buffer)
                    self._buffer.clear()
                    break

                end = self._buffer.find(SYM_CRLF)
                if end == -1:
                    return messages  # incomplete inline line: wait for more
                # split like redis does: runs of whitespace separate tokens
                tokens = bytes(self._buffer[:end]).split()
                del self._buffer[: end + 2]
                messages.append(tokens)
            else:
                data = b""

        try:
            if data:
                self._reader.feed(data)
                self._fed += len(data)
                if (
                    not self._boundary_unknown
                    and self._fed - self._consumed > self.MAX_BUFFER
                ):
                    # a peer announced a giant payload and keeps
                    # delivering it: hiredis buffers it internally, so
                    # cap the in-flight bytes like the python engine
                    # caps its buffer (the check needs canonical
                    # lengths, which null/error messages do not have)
                    raise ProtocolError("request exceeds maximum allowed size")
            while True:
                message = self._reader.gets()
                if message is False:  # hiredis: no complete message buffered
                    break
                # None is a legitimate parsed value (null bulk / null array)
                messages.append(message)
                wire_len = _wire_length(message)
                if wire_len is None:
                    self._boundary_unknown = True
                else:
                    self._consumed += wire_len
        except hiredis.HiredisError as exc:
            raise ProtocolError(str(exc))

        if (
            self._engaged
            and not self._boundary_unknown
            and self._fed
            and self._fed == self._consumed
        ):
            # every byte handed to hiredis has been parsed: it is back at
            # a message boundary, so inline interception can resume
            self._engaged = False
            self._fed = 0
            self._consumed = 0
        return messages

    def _feed_python(self, data):
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
