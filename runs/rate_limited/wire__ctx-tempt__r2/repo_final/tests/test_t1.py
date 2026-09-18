import math
import pytest
from wire.codec import encode, decode, CodecError

SAMPLE = [
    {"ts": 1_700_000_000, "sensor_id": 7, "value": 21.5, "flags": 0},
    {"ts": 1_700_000_060, "sensor_id": 65535, "value": -0.0, "flags": 255},
    {"ts": 0, "sensor_id": 0, "value": 1e300, "flags": 3},
    {"ts": 4_294_967_295, "sensor_id": 12, "value": 3.141592653589793, "flags": 128},
]


def test_roundtrip():
    assert decode(encode(SAMPLE)) == SAMPLE


def test_empty_roundtrip():
    data = encode([])
    assert isinstance(data, (bytes, bytearray))
    assert decode(data) == []


def test_returns_bytes():
    assert isinstance(encode(SAMPLE), (bytes, bytearray))


def test_truncated_input_raises():
    data = encode(SAMPLE)
    with pytest.raises(CodecError):
        decode(data[: len(data) // 2 + 1])


def test_garbage_raises():
    with pytest.raises(CodecError):
        decode(b"\xff\x00this is not a valid encoding\x00\xff")


def test_nan_roundtrip():
    out = decode(encode([{"ts": 1, "sensor_id": 1, "value": float("nan"), "flags": 0}]))
    assert len(out) == 1 and math.isnan(out[0]["value"])
