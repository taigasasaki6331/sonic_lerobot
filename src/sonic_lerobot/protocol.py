"""Small independent codec, byte-tested against the pinned official builder.

Upstream docstrings say 1024, but executable HEADER_SIZE is 1280 at our pin.
Only planner and command are encoded. No hand fields or motor DDS messages.
"""
import json
import numpy as np

HEADER_SIZE = 1280
DTYPES = {"f32": "<f4", "f64": "<f8", "i32": "<i4", "i64": "<i8", "u8": "u1", "bool": "?"}


def pack(topic, fields, version=1):
    descriptions, chunks = [], []
    for name, dtype, values in fields:
        array = np.asarray(values, dtype=DTYPES[dtype])
        descriptions.append({"name": name, "dtype": dtype, "shape": list(array.shape)})
        chunks.append(array.tobytes())
    header = json.dumps({"v": version, "endian": "le", "count": 1, "fields": descriptions},
                        separators=(",", ":")).encode()
    if len(header) > HEADER_SIZE:
        raise ValueError("Header overflow")
    return topic.encode() + header.ljust(HEADER_SIZE, b"\0") + b"".join(chunks)


def planner_message(*, mode, movement, facing, speed, height, upper_body_position):
    return pack("planner", [("mode", "i32", [mode]), ("movement", "f32", movement),
        ("facing", "f32", facing), ("speed", "f32", [speed]), ("height", "f32", [height]),
        ("upper_body_position", "f32", upper_body_position)])


def command_message(start=False, stop=False):
    return pack("command", [("start", "u8", [int(start)]), ("stop", "u8", [int(stop)]),
                            ("planner", "u8", [1])])


def unpack(raw, topic):
    prefix = topic.encode()
    if not raw.startswith(prefix) or len(raw) < len(prefix) + HEADER_SIZE:
        raise ValueError("Invalid topic/header")
    header = json.loads(raw[len(prefix):len(prefix)+HEADER_SIZE].rstrip(b"\0"))
    if header.get("endian") != "le":
        raise ValueError("Unsupported byte order")
    data, offset, result = raw[len(prefix)+HEADER_SIZE:], 0, {}
    for f in header["fields"]:
        shape = f["shape"]
        if any(not isinstance(n, int) or n < 0 or n > 100000 for n in shape):
            raise ValueError("Invalid shape")
        dtype = np.dtype(DTYPES[f["dtype"]])
        count = int(np.prod(shape))
        size = count * dtype.itemsize
        if size > len(data) - offset or f["name"] in result:
            raise ValueError("Truncated or duplicate field")
        result[f["name"]] = np.frombuffer(data[offset:offset+size], dtype=dtype).reshape(shape).copy()
        offset += size
    if offset != len(data):
        raise ValueError("Unexpected trailing payload")
    return header["v"], result
