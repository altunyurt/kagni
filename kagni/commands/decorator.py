from functools import partial, reduce, wraps
import inspect
from kagni.resp import protocolBuilder

CASTERS = {
    "bytes_to_int": lambda arg: int(arg, base=10),
    "bytes_to_str": lambda arg: arg.decode(),
}


def command_decorator(name):
    def wrapper(f):

        f_specs = inspect.getfullargspec(f)
        f_args = f_specs.args[1:]  # exclude self
        f_varargs = f_specs.varargs
        f_annotations = f_specs.annotations

        @wraps(f)
        def inner(instance, *c_args):  # calling args
            args_list = []

            if f_args:

                for arg_name, arg in zip(f_args, c_args):
                    _type = f_annotations.get(arg_name)
                    if _type and _type != bytes:
                        arg = CASTERS[f"bytes_to_{_type.__name__}"](arg)

                    args_list.append(arg)

            if f_varargs:
                # push the rest of varargs in
                args_list.extend(c_args[len(f_args) :])

            retval = f(instance, *args_list)
            return protocolBuilder(retval)

        return inner

    return wrapper
