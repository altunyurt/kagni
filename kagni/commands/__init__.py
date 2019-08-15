import logging

from .basic import CommandSetMixin as BasicMixin
from .set import CommandSetMixin as SetMixin
from .bit import CommandSetMixin as BitMixin
from .hash import CommandSetMixin as HashMixin

# from .data import self.data


__all__ = ["Commands"]


# register command to commands repo
class Commands(BasicMixin, SetMixin, BitMixin, HashMixin):
    def __init__(self, data=None):
        self.data = data if data is not None else {}
