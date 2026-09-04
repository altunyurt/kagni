import logging

from .basic import CommandSetMixin as BasicMixin
from .set import CommandSetMixin as SetMixin
from .bit import CommandSetMixin as BitMixin
from .hash import CommandSetMixin as HashMixin
from .lists import CommandSetMixin as ListMixin
from kagni.constants import Error, Errors
from kagni.data import Data
from kagni.resp import protocolBuilder

log = logging.getLogger(__name__)

__all__ = ["Commands"]


class Commands(BasicMixin, SetMixin, BitMixin, HashMixin, ListMixin):
    def __init__(self, data=None):
        self.data = data if data is not None else Data()
        # optional snapshot backend, wired by the servers; FLUSHDB/FLUSHALL
        # wipe it together with the in-memory state
        self.persistence = None

    def dispatch(self, request):
        """Execute one parsed request (``[command, *args]``) and return the
        RESP reply bytes.

        Unknown commands and arity errors produce proper ``-ERR`` replies,
        command errors (``Error``) are encoded as RESP errors, and nothing
        here ever raises, so a bad request cannot kill the connection.
        Returns None for empty requests (no reply is sent).
        """
        if not isinstance(request, list) or not request:
            return None

        command = request[0]
        if not isinstance(command, bytes):
            return protocolBuilder(Error("ERR", "invalid request"))
        name = command.decode("ascii", "replace")
        handler = getattr(self, name.upper(), None)
        if handler is None:
            return protocolBuilder(Error("ERR", "unknown command '{}'".format(name)))

        args = request[1:]
        if len(args) < handler.min_args or (
            handler.max_args is not None and len(args) > handler.max_args
        ):
            return protocolBuilder(Errors.arity(name.lower()))

        try:
            return handler(*args)
        except Error as exc:
            return protocolBuilder(exc)
        except Exception:
            log.exception("command %r failed", name)
            return protocolBuilder(Error("ERR", "internal error"))
