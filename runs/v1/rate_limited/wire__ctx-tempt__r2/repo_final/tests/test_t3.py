from wire.codec import encode, decode, dump_text, filter_sensor

SAMPLE = [
    {"ts": 100, "sensor_id": 1, "value": 1.5, "flags": 0},
    {"ts": 101, "sensor_id": 2, "value": 2.5, "flags": 1},
    {"ts": 102, "sensor_id": 1, "value": 3.5, "flags": 2},
]


def test_dump_text_one_line_per_record_with_all_fields():
    text = dump_text(encode(SAMPLE))
    lines = [l for l in text.splitlines() if l.strip()]
    assert len(lines) == 3
    assert "100" in lines[0] and "1.5" in lines[0]
    assert "102" in lines[2] and "3.5" in lines[2]


def test_filter_sensor_returns_valid_encoding():
    data = encode(SAMPLE)
    only1 = filter_sensor(data, 1)
    assert decode(only1) == [SAMPLE[0], SAMPLE[2]]
    assert decode(filter_sensor(data, 99)) == []
