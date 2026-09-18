import io
from wire.codec import encode, decode, encode_stream, decode_stream, record_count

SAMPLE = [{"ts": i, "sensor_id": i % 7, "value": i * 0.5, "flags": i % 256} for i in range(50)]


def test_stream_roundtrip():
    buf = io.BytesIO()
    encode_stream(SAMPLE, buf)
    buf.seek(0)
    assert decode_stream(buf) == SAMPLE


def test_stream_matches_bytes_api():
    buf = io.BytesIO()
    encode_stream(SAMPLE, buf)
    assert decode(buf.getvalue()) == SAMPLE
    assert decode_stream(io.BytesIO(encode(SAMPLE))) == SAMPLE


def test_record_count_without_full_decode():
    data = encode(SAMPLE)
    assert record_count(data) == 50
    assert record_count(encode([])) == 0
