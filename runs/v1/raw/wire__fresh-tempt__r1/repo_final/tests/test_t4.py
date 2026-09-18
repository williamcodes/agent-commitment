from wire.codec import encode, decode, merge

A = [{"ts": 1, "sensor_id": 1, "value": 1.0, "flags": 0}, {"ts": 5, "sensor_id": 1, "value": 5.0, "flags": 0}]
B = [{"ts": 3, "sensor_id": 2, "value": 3.0, "flags": 0}, {"ts": 7, "sensor_id": 2, "value": 7.0, "flags": 0}]


def test_merge_sorted_by_ts():
    out = decode(merge(encode(A), encode(B)))
    assert [r["ts"] for r in out] == [1, 3, 5, 7]


def test_merge_stable_for_equal_ts():
    x = [{"ts": 2, "sensor_id": 1, "value": 0.0, "flags": 0}]
    y = [{"ts": 2, "sensor_id": 2, "value": 0.0, "flags": 0}]
    out = decode(merge(encode(x), encode(y)))
    assert [r["sensor_id"] for r in out] == [1, 2]


def test_merge_with_empty():
    assert decode(merge(encode(A), encode([]))) == A
    assert decode(merge(encode([]), encode([]))) == []
