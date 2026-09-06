from functools import wraps
import inspect

from kagni.constants import Errors
from kagni.resp import protocolBuilder
from .common import string2ll

CASTERS = {
    # redis string2ll semantics: rejects '+', whitespace, leading zeros
    # and anything outside the signed 64-bit range (raises ValueError,
    # translated to NOT_INT below)
    "bytes_to_int": string2ll,
    "bytes_to_str": lambda arg: arg.decode(),
}


def command_decorator(name):
    """Wrap a command method so that it:

    - converts the typed (non-bytes) arguments from the wire, raising
      ``Errors.NOT_INT`` instead of a raw ``ValueError`` on bad input,
    - encodes the return value into a RESP reply,
    - exposes ``min_args`` / ``max_args`` so the dispatcher can reject
      wrong-arity calls with a proper redis-style error before the method
      body runs.
    """
    def wrapper(f):

        f_specs = inspect.getfullargspec(f)
        f_args = f_specs.args[1:]  # exclude self
        f_varargs = f_specs.varargs is not None
        f_annotations = f_specs.annotations
        required = len(f_args) - len(f_specs.defaults or ())

        # resolve the per-argument casters once, at decoration time
        casters = []
        for arg_name in f_args:
            _type = f_annotations.get(arg_name)
            if _type is not None and _type is not bytes:
                casters.append(CASTERS[f"bytes_to_{_type.__name__}"])
            else:
                casters.append(None)

        @wraps(f)
        def inner(instance, *c_args):  # calling args
            args_list = []
            for caster, arg in zip(casters, c_args):
                if caster is None:
                    args_list.append(arg)
                else:
                    try:
                        args_list.append(caster(arg))
                    except (ValueError, TypeError):
                        raise Errors.NOT_INT

            if f_varargs:
                # push the rest of varargs in
                args_list.extend(c_args[len(casters):])

            retval = f(instance, *args_list)
            return protocolBuilder(retval)

        inner.min_args = required
        inner.max_args = None if f_varargs else len(f_args)
        inner.command_name = name
        return inner

    return wrapper
