from kagni.constants import Response

__all__ = ["test_sequence"]

test_sequence = [
    ##
    # LPUSH / RPUSH
    ##
    {
        "name": "Check LPUSH on missing key creates the list",
        "command": "LPUSH",
        "args": [b"k", b"a"],
        "returns": 1,
        "expects": lambda cs: list(cs.data[b"k"]) == [b"a"],
    },
    {
        "name": "Check LPUSH return value for multiple values",
        "command": "LPUSH",
        "args": [b"k", b"a", b"b", b"c"],
        "returns": 3,
        "expects": lambda cs: list(cs.data[b"k"]) == [b"c", b"b", b"a"],
    },
    {
        "name": "Check LPUSH ordering when pushing onto an existing list",
        "command": "LPUSH",
        "args": [b"k", b"c", b"d"],
        "depends": [{"command": "LPUSH", "args": [b"k", b"a", b"b"], "returns": 2}],
        "returns": 4,
        "expects": lambda cs: list(cs.data[b"k"]) == [b"d", b"c", b"b", b"a"],
    },
    {
        "name": "Check RPUSH on missing key creates the list",
        "command": "RPUSH",
        "args": [b"k", b"a"],
        "returns": 1,
        "expects": lambda cs: list(cs.data[b"k"]) == [b"a"],
    },
    {
        "name": "Check RPUSH return value and ordering for multiple values",
        "command": "RPUSH",
        "args": [b"k", b"a", b"b", b"c"],
        "returns": 3,
        "expects": lambda cs: list(cs.data[b"k"]) == [b"a", b"b", b"c"],
    },
    {
        "name": "Check RPUSH appends after LPUSH",
        "command": "RPUSH",
        "args": [b"k", b"c", b"d"],
        "depends": [{"command": "LPUSH", "args": [b"k", b"a", b"b"], "returns": 2}],
        "returns": 4,
        "expects": lambda cs: list(cs.data[b"k"]) == [b"b", b"a", b"c", b"d"],
    },
    {
        "name": "Check LPUSHX on a missing key is a no-op",
        "command": "LPUSHX",
        "args": [b"k", b"a"],
        "returns": 0,
        "expects": lambda cs: b"k" not in cs.data,
    },
    {
        "name": "Check LPUSHX return value on an existing list",
        "command": "LPUSHX",
        "args": [b"k", b"c"],
        "depends": [{"command": "LPUSH", "args": [b"k", b"a", b"b"], "returns": 2}],
        "returns": 3,
        "expects": lambda cs: list(cs.data[b"k"]) == [b"c", b"b", b"a"],
    },
    {
        "name": "Check RPUSHX on a missing key is a no-op",
        "command": "RPUSHX",
        "args": [b"k", b"a"],
        "returns": 0,
        "expects": lambda cs: b"k" not in cs.data,
    },
    {
        "name": "Check RPUSHX return value on an existing list",
        "command": "RPUSHX",
        "args": [b"k", b"c"],
        "depends": [{"command": "RPUSH", "args": [b"k", b"a", b"b"], "returns": 2}],
        "returns": 3,
        "expects": lambda cs: list(cs.data[b"k"]) == [b"a", b"b", b"c"],
    },
    ##
    # LLEN
    ##
    {
        "name": "Check LLEN on a missing key",
        "command": "LLEN",
        "args": [b"k"],
        "returns": 0,
    },
    {
        "name": "Check LLEN return value",
        "command": "LLEN",
        "args": [b"k"],
        "depends": [{"command": "RPUSH", "args": [b"k", b"a", b"b", b"c"], "returns": 3}],
        "returns": 3,
    },
    ##
    # LRANGE
    ##
    {
        "name": "Check LRANGE on a missing key",
        "command": "LRANGE",
        "args": [b"k", b"0", b"-1"],
        "returns": [],
    },
    {
        "name": "Check LRANGE full range",
        "command": "LRANGE",
        "args": [b"k", b"0", b"-1"],
        "depends": [
            {"command": "RPUSH", "args": [b"k", b"a", b"b", b"c", b"d", b"e"], "returns": 5}
        ],
        "returns": [b"a", b"b", b"c", b"d", b"e"],
    },
    {
        "name": "Check LRANGE positive sub-range",
        "command": "LRANGE",
        "args": [b"k", b"1", b"3"],
        "depends": [
            {"command": "RPUSH", "args": [b"k", b"a", b"b", b"c", b"d", b"e"], "returns": 5}
        ],
        "returns": [b"b", b"c", b"d"],
    },
    {
        "name": "Check LRANGE negative offsets",
        "command": "LRANGE",
        "args": [b"k", b"-3", b"-1"],
        "depends": [
            {"command": "RPUSH", "args": [b"k", b"a", b"b", b"c", b"d", b"e"], "returns": 5}
        ],
        "returns": [b"c", b"d", b"e"],
    },
    {
        "name": "Check LRANGE negative start with positive end",
        "command": "LRANGE",
        "args": [b"k", b"-2", b"10"],
        "depends": [
            {"command": "RPUSH", "args": [b"k", b"a", b"b", b"c", b"d", b"e"], "returns": 5}
        ],
        "returns": [b"d", b"e"],
    },
    {
        "name": "Check LRANGE with start greater than end",
        "command": "LRANGE",
        "args": [b"k", b"4", b"2"],
        "depends": [
            {"command": "RPUSH", "args": [b"k", b"a", b"b", b"c", b"d", b"e"], "returns": 5}
        ],
        "returns": [],
    },
    {
        "name": "Check LRANGE clamps end beyond the list",
        "command": "LRANGE",
        "args": [b"k", b"3", b"99"],
        "depends": [
            {"command": "RPUSH", "args": [b"k", b"a", b"b", b"c", b"d", b"e"], "returns": 5}
        ],
        "returns": [b"d", b"e"],
    },
    {
        "name": "Check LRANGE with start beyond the list",
        "command": "LRANGE",
        "args": [b"k", b"99", b"100"],
        "depends": [
            {"command": "RPUSH", "args": [b"k", b"a", b"b", b"c", b"d", b"e"], "returns": 5}
        ],
        "returns": [],
    },
    {
        "name": "Check LRANGE with very negative end",
        "command": "LRANGE",
        "args": [b"k", b"0", b"-99"],
        "depends": [
            {"command": "RPUSH", "args": [b"k", b"a", b"b", b"c", b"d", b"e"], "returns": 5}
        ],
        "returns": [],
    },
    ##
    # LINDEX
    ##
    {
        "name": "Check LINDEX on a missing key",
        "command": "LINDEX",
        "args": [b"k", b"0"],
        "returns": Response.NIL,
    },
    {
        "name": "Check LINDEX first element",
        "command": "LINDEX",
        "args": [b"k", b"0"],
        "depends": [{"command": "RPUSH", "args": [b"k", b"a", b"b", b"c"], "returns": 3}],
        "returns": b"a",
    },
    {
        "name": "Check LINDEX last element via negative index",
        "command": "LINDEX",
        "args": [b"k", b"-1"],
        "depends": [{"command": "RPUSH", "args": [b"k", b"a", b"b", b"c"], "returns": 3}],
        "returns": b"c",
    },
    {
        "name": "Check LINDEX middle element",
        "command": "LINDEX",
        "args": [b"k", b"1"],
        "depends": [{"command": "RPUSH", "args": [b"k", b"a", b"b", b"c"], "returns": 3}],
        "returns": b"b",
    },
    {
        "name": "Check LINDEX out of range returns nil",
        "command": "LINDEX",
        "args": [b"k", b"99"],
        "depends": [{"command": "RPUSH", "args": [b"k", b"a", b"b", b"c"], "returns": 3}],
        "returns": Response.NIL,
    },
    {
        "name": "Check LINDEX negative out of range returns nil",
        "command": "LINDEX",
        "args": [b"k", b"-99"],
        "depends": [{"command": "RPUSH", "args": [b"k", b"a", b"b", b"c"], "returns": 3}],
        "returns": Response.NIL,
    },
    ##
    # LSET
    ##
    {
        "name": "Check LSET updates an element",
        "command": "LSET",
        "args": [b"k", b"1", b"X"],
        "depends": [{"command": "RPUSH", "args": [b"k", b"a", b"b", b"c"], "returns": 3}],
        "returns": Response.OK,
        "expects": lambda cs: list(cs.data[b"k"]) == [b"a", b"X", b"c"],
    },
    {
        "name": "Check LSET with negative index updates the tail",
        "command": "LSET",
        "args": [b"k", b"-1", b"Z"],
        "depends": [{"command": "RPUSH", "args": [b"k", b"a", b"b", b"c"], "returns": 3}],
        "returns": Response.OK,
        "expects": lambda cs: list(cs.data[b"k"]) == [b"a", b"b", b"Z"],
    },
    ##
    # LTRIM
    ##
    {
        "name": "Check LTRIM on a missing key",
        "command": "LTRIM",
        "args": [b"k", b"0", b"-1"],
        "returns": Response.OK,
    },
    {
        "name": "Check LTRIM keeps the middle of the list",
        "command": "LTRIM",
        "args": [b"k", b"1", b"3"],
        "depends": [
            {"command": "RPUSH", "args": [b"k", b"a", b"b", b"c", b"d", b"e"], "returns": 5}
        ],
        "returns": Response.OK,
        "expects": lambda cs: list(cs.data[b"k"]) == [b"b", b"c", b"d"],
    },
    {
        "name": "Check LTRIM clamps the end beyond the list",
        "command": "LTRIM",
        "args": [b"k", b"3", b"99"],
        "depends": [
            {"command": "RPUSH", "args": [b"k", b"a", b"b", b"c", b"d", b"e"], "returns": 5}
        ],
        "returns": Response.OK,
        "expects": lambda cs: list(cs.data[b"k"]) == [b"d", b"e"],
    },
    {
        "name": "Check LTRIM with negative offsets",
        "command": "LTRIM",
        "args": [b"k", b"-3", b"-2"],
        "depends": [
            {"command": "RPUSH", "args": [b"k", b"a", b"b", b"c", b"d", b"e"], "returns": 5}
        ],
        "returns": Response.OK,
        "expects": lambda cs: list(cs.data[b"k"]) == [b"c", b"d"],
    },
    {
        "name": "Check LTRIM deleting the whole list removes the key",
        "command": "LTRIM",
        "args": [b"k", b"5", b"10"],
        "depends": [{"command": "RPUSH", "args": [b"k", b"a", b"b"], "returns": 2}],
        "returns": Response.OK,
        "expects": lambda cs: b"k" not in cs.data,
    },
    {
        "name": "Check LTRIM with start greater than end removes the key",
        "command": "LTRIM",
        "args": [b"k", b"3", b"1"],
        "depends": [{"command": "RPUSH", "args": [b"k", b"a", b"b"], "returns": 2}],
        "returns": Response.OK,
        "expects": lambda cs: b"k" not in cs.data,
    },
    {
        "name": "Check LTRIM to the full list is a no-op",
        "command": "LTRIM",
        "args": [b"k", b"0", b"-1"],
        "depends": [{"command": "RPUSH", "args": [b"k", b"a", b"b"], "returns": 2}],
        "returns": Response.OK,
        "expects": lambda cs: list(cs.data[b"k"]) == [b"a", b"b"],
    },
    ##
    # LPOP / RPOP
    ##
    {
        "name": "Check LPOP on a missing key",
        "command": "LPOP",
        "args": [b"k"],
        "returns": Response.NIL,
    },
    {
        "name": "Check LPOP with count on a missing key returns null array",
        "command": "LPOP",
        "args": [b"k", b"5"],
        "returns": Response.NIL_ARRAY,
    },
    {
        "name": "Check LPOP pops from the head",
        "command": "LPOP",
        "args": [b"k"],
        "depends": [{"command": "RPUSH", "args": [b"k", b"a", b"b"], "returns": 2}],
        "returns": b"a",
        "expects": lambda cs: list(cs.data[b"k"]) == [b"b"],
    },
    {
        "name": "Check LPOP removing the last element deletes the key",
        "command": "LPOP",
        "args": [b"k"],
        "depends": [{"command": "RPUSH", "args": [b"k", b"a"], "returns": 1}],
        "returns": b"a",
        "expects": lambda cs: b"k" not in cs.data,
    },
    {
        "name": "Check LPOP with count pops head-first",
        "command": "LPOP",
        "args": [b"k", b"2"],
        "depends": [
            {"command": "RPUSH", "args": [b"k", b"a", b"b", b"c", b"d"], "returns": 4}
        ],
        "returns": [b"a", b"b"],
        "expects": lambda cs: list(cs.data[b"k"]) == [b"c", b"d"],
    },
    {
        "name": "Check LPOP with count bigger than the list pops everything",
        "command": "LPOP",
        "args": [b"k", b"10"],
        "depends": [{"command": "RPUSH", "args": [b"k", b"a", b"b"], "returns": 2}],
        "returns": [b"a", b"b"],
        "expects": lambda cs: b"k" not in cs.data,
    },
    {
        "name": "Check LPOP with count zero returns an empty array",
        "command": "LPOP",
        "args": [b"k", b"0"],
        "depends": [{"command": "RPUSH", "args": [b"k", b"a", b"b"], "returns": 2}],
        "returns": [],
        "expects": lambda cs: list(cs.data[b"k"]) == [b"a", b"b"],
    },
    {
        "name": "Check RPOP pops from the tail",
        "command": "RPOP",
        "args": [b"k"],
        "depends": [{"command": "RPUSH", "args": [b"k", b"a", b"b"], "returns": 2}],
        "returns": b"b",
        "expects": lambda cs: list(cs.data[b"k"]) == [b"a"],
    },
    {
        "name": "Check RPOP with count returns tail-first",
        "command": "RPOP",
        "args": [b"k", b"2"],
        "depends": [
            {"command": "RPUSH", "args": [b"k", b"a", b"b", b"c", b"d"], "returns": 4}
        ],
        "returns": [b"d", b"c"],
        "expects": lambda cs: list(cs.data[b"k"]) == [b"a", b"b"],
    },
    {
        "name": "Check RPOP with count bigger than the list pops everything",
        "command": "RPOP",
        "args": [b"k", b"10"],
        "depends": [{"command": "RPUSH", "args": [b"k", b"a", b"b"], "returns": 2}],
        "returns": [b"b", b"a"],
        "expects": lambda cs: b"k" not in cs.data,
    },
    {
        "name": "Check RPOP on a missing key",
        "command": "RPOP",
        "args": [b"k"],
        "returns": Response.NIL,
    },
    ##
    # LREM
    ##
    {
        "name": "Check LREM on a missing key",
        "command": "LREM",
        "args": [b"k", b"0", b"a"],
        "returns": 0,
    },
    {
        "name": "Check LREM with count zero removes all matches",
        "command": "LREM",
        "args": [b"k", b"0", b"a"],
        "depends": [
            {"command": "RPUSH", "args": [b"k", b"a", b"b", b"a", b"c", b"a"], "returns": 6}
        ],
        "returns": 3,
        "expects": lambda cs: list(cs.data[b"k"]) == [b"b", b"c"],
    },
    {
        "name": "Check LREM with positive count removes from the head",
        "command": "LREM",
        "args": [b"k", b"1", b"a"],
        "depends": [
            {"command": "RPUSH", "args": [b"k", b"a", b"b", b"a", b"c", b"a"], "returns": 6}
        ],
        "returns": 1,
        "expects": lambda cs: list(cs.data[b"k"]) == [b"b", b"a", b"c", b"a"],
    },
    {
        "name": "Check LREM with negative count removes from the tail",
        "command": "LREM",
        "args": [b"k", b"-1", b"a"],
        "depends": [
            {"command": "RPUSH", "args": [b"k", b"a", b"b", b"a", b"c", b"a"], "returns": 6}
        ],
        "returns": 1,
        "expects": lambda cs: list(cs.data[b"k"]) == [b"a", b"b", b"a", b"c"],
    },
    {
        "name": "Check LREM with negative count removes several from the tail",
        "command": "LREM",
        "args": [b"k", b"-2", b"a"],
        "depends": [
            {"command": "RPUSH", "args": [b"k", b"a", b"b", b"a", b"c", b"a"], "returns": 6}
        ],
        "returns": 2,
        "expects": lambda cs: list(cs.data[b"k"]) == [b"a", b"b", b"c"],
    },
    {
        "name": "Check LREM with no matches",
        "command": "LREM",
        "args": [b"k", b"0", b"zz"],
        "depends": [{"command": "RPUSH", "args": [b"k", b"a", b"b"], "returns": 2}],
        "returns": 0,
        "expects": lambda cs: list(cs.data[b"k"]) == [b"a", b"b"],
    },
    {
        "name": "Check LREM removing everything deletes the key",
        "command": "LREM",
        "args": [b"k", b"0", b"a"],
        "depends": [{"command": "RPUSH", "args": [b"k", b"a", b"a"], "returns": 2}],
        "returns": 2,
        "expects": lambda cs: b"k" not in cs.data,
    },
    ##
    # LINSERT
    ##
    {
        "name": "Check LINSERT on a missing key",
        "command": "LINSERT",
        "args": [b"k", b"BEFORE", b"a", b"X"],
        "returns": 0,
    },
    {
        "name": "Check LINSERT with a missing pivot",
        "command": "LINSERT",
        "args": [b"k", b"BEFORE", b"zz", b"X"],
        "depends": [{"command": "RPUSH", "args": [b"k", b"a", b"b"], "returns": 2}],
        "returns": -1,
    },
    {
        "name": "Check LINSERT BEFORE an element",
        "command": "LINSERT",
        "args": [b"k", b"BEFORE", b"b", b"X"],
        "depends": [{"command": "RPUSH", "args": [b"k", b"a", b"b"], "returns": 2}],
        "returns": 3,
        "expects": lambda cs: list(cs.data[b"k"]) == [b"a", b"X", b"b"],
    },
    {
        "name": "Check LINSERT AFTER an element",
        "command": "LINSERT",
        "args": [b"k", b"AFTER", b"a", b"X"],
        "depends": [{"command": "RPUSH", "args": [b"k", b"a", b"b"], "returns": 2}],
        "returns": 3,
        "expects": lambda cs: list(cs.data[b"k"]) == [b"a", b"X", b"b"],
    },
    {
        "name": "Check LINSERT BEFORE the head element",
        "command": "LINSERT",
        "args": [b"k", b"BEFORE", b"a", b"X"],
        "depends": [{"command": "RPUSH", "args": [b"k", b"a"], "returns": 1}],
        "returns": 2,
        "expects": lambda cs: list(cs.data[b"k"]) == [b"X", b"a"],
    },
    {
        "name": "Check LINSERT is case-insensitive on the where argument",
        "command": "LINSERT",
        "args": [b"k", b"after", b"a", b"X"],
        "depends": [{"command": "RPUSH", "args": [b"k", b"a", b"b"], "returns": 2}],
        "returns": 3,
        "expects": lambda cs: list(cs.data[b"k"]) == [b"a", b"X", b"b"],
    },
]
