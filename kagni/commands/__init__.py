from collections import deque
from functools import partial, reduce
from math import ceil
import logging

from kagni.constants import Errors, OK, NIL, PONG
from kagni.data import Data

from .basic import CommandSetMixin as BasicMixin
from .set import CommandSetMixin as SetMixin
from .bit import CommandSetMixin as BitMixin
from .hash import CommandSetMixin as HashMixin

# from .data import self.data

log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)
log.addHandler(logging.StreamHandler())


__all__ = ["Commands"]


# https://github.com/chekart/rediserver


# register command to commands repo
class Commands(BasicMixin, SetMixin, BitMixin, HashMixin):
    def __init__(self, data=None):
        self.data = data if data is not None else {}
