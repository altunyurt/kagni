class RESP:
    def __init__(self, data):
        self.data = data.split(b"\r\n")
        self.pos = 0
        self.len = len(self.data)

    def __iter__(self):
        return self

    def __next__(self):
        if self.pos >= self.len - 1:
            raise StopIteration()
        data = self.data[self.pos]
        self.pos += 1
        return data


def parse(payload):
    # payload.0 = "$2"

    _header = next(payload)
    _type = chr(_header[0])

    # TODO: type and length check according to protocol defs
    if _type == ":":
        return float(_header[1:])

    if _type == "$":
        return next(payload)

    if _type == "*":
        _l = int(_header[1:])
        return [parse(payload) for i in range(_l)]

    raise NotImplementedError(f"Unknown message type: {_type}")


def protocolParser(_data):
    resp = RESP(_data)
    return parse(resp)
