"""Compact binary codec for sensor log records (SPEC.md, Approach A).

Wire layout (all integers little-endian):

    header   : magic b"WIRE" | version u8 (=1) | count u32
    records  : count * ( ts u32 | sensor_id u16 | value f64 | flags u8 )   (15 bytes each)
    trailer  : crc32 u32 over header + records

The record count makes truncation detectable, and the CRC32 trailer makes
corruption of any byte detectable. The whole stream is length-checked exactly,
so trailing garbage is rejected as well.
"""

from __future__ import annotations

import struct
import zlib

__all__ = [
    "encode",
    "decode",
    "encode_stream",
    "decode_stream",
    "record_count",
    "dump_text",
    "filter_sensor",
    "merge",
    "CodecError",
]

MAGIC = b"WIRE"
VERSION = 1

_HEADER = struct.Struct("<4sBI")
_RECORD = struct.Struct("<IHdB")
_TRAILER = struct.Struct("<I")

FIELDS = ("ts", "sensor_id", "value", "flags")
_INT_RANGES = {
    "ts": (0, 2**32 - 1),
    "sensor_id": (0, 2**16 - 1),
    "flags": (0, 2**8 - 1),
}


class CodecError(Exception):
    """Raised by decode() on truncated or corrupted input."""


def _validate(record: dict, index: int) -> tuple[int, int, float, int]:
    if not isinstance(record, dict):
        raise TypeError(f"record {index}: expected dict, got {type(record).__name__}")
    if set(record) != set(FIELDS):
        missing = sorted(set(FIELDS) - set(record))
        extra = sorted(set(record) - set(FIELDS))
        raise ValueError(f"record {index}: missing fields {missing}, unexpected fields {extra}")
    for name, (lo, hi) in _INT_RANGES.items():
        v = record[name]
        # bool is an int subclass; reject it explicitly to keep the round trip exact.
        if isinstance(v, bool) or not isinstance(v, int):
            raise TypeError(f"record {index}: {name!r} must be int, got {type(v).__name__}")
        if not lo <= v <= hi:
            raise ValueError(f"record {index}: {name!r}={v} out of range {lo}..{hi}")
    value = record["value"]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"record {index}: 'value' must be float, got {type(value).__name__}")
    return record["ts"], record["sensor_id"], float(value), record["flags"]


def encode(records: list[dict]) -> bytes:
    """Serialize records to a self-contained byte string."""
    if not isinstance(records, (list, tuple)):
        raise TypeError(f"records must be a list, got {type(records).__name__}")
    if len(records) > 2**32 - 1:
        raise ValueError("too many records")

    out = bytearray(_HEADER.pack(MAGIC, VERSION, len(records)))
    for i, rec in enumerate(records):
        out += _RECORD.pack(*_validate(rec, i))
    out += _TRAILER.pack(zlib.crc32(out) & 0xFFFFFFFF)
    return bytes(out)


def _check_frame(data: bytes) -> tuple[int, int]:
    """Validate header, length and checksum; return (count, body_end).

    Does not touch the record payload beyond hashing it, so callers can
    inspect the frame without materializing records.
    """
    if not isinstance(data, (bytes, bytearray, memoryview)):
        raise CodecError(f"expected bytes, got {type(data).__name__}")
    data = bytes(data)

    if len(data) < _HEADER.size + _TRAILER.size:
        raise CodecError(f"input too short ({len(data)} bytes)")

    magic, version, count = _HEADER.unpack_from(data, 0)
    if magic != MAGIC:
        raise CodecError(f"bad magic {magic!r}")
    if version != VERSION:
        raise CodecError(f"unsupported version {version}")

    expected = _HEADER.size + count * _RECORD.size + _TRAILER.size
    if len(data) < expected:
        raise CodecError(f"truncated: expected {expected} bytes, got {len(data)}")
    if len(data) > expected:
        raise CodecError(f"trailing data: expected {expected} bytes, got {len(data)}")

    body_end = expected - _TRAILER.size
    (stored_crc,) = _TRAILER.unpack_from(data, body_end)
    actual_crc = zlib.crc32(data[:body_end]) & 0xFFFFFFFF
    if stored_crc != actual_crc:
        raise CodecError(f"checksum mismatch: stored {stored_crc:#010x}, computed {actual_crc:#010x}")

    return count, body_end


def decode(data: bytes) -> list[dict]:
    """Parse bytes produced by encode(); raises CodecError on bad input."""
    data = bytes(data) if isinstance(data, (bytearray, memoryview)) else data
    _, body_end = _check_frame(data)
    return [
        {"ts": ts, "sensor_id": sid, "value": value, "flags": flags}
        for ts, sid, value, flags in _RECORD.iter_unpack(data[_HEADER.size:body_end])
    ]


def record_count(data: bytes) -> int:
    """Return the number of records in an encoded frame without building them.

    The frame is still fully validated (header, length, checksum), so a
    truncated or corrupted input raises CodecError just as decode() would.
    """
    count, _ = _check_frame(data)
    return count


def encode_stream(records: list[dict], fp) -> None:
    """Write records to a binary file object in the same format as encode().

    Records are written incrementally with a running CRC, so the whole
    encoding is never held in memory.
    """
    if not isinstance(records, (list, tuple)):
        raise TypeError(f"records must be a list, got {type(records).__name__}")
    if len(records) > 2**32 - 1:
        raise ValueError("too many records")

    header = _HEADER.pack(MAGIC, VERSION, len(records))
    crc = zlib.crc32(header)
    fp.write(header)
    for i, rec in enumerate(records):
        chunk = _RECORD.pack(*_validate(rec, i))
        crc = zlib.crc32(chunk, crc)
        fp.write(chunk)
    fp.write(_TRAILER.pack(crc & 0xFFFFFFFF))


def decode_stream(fp) -> list[dict]:
    """Read one encoded frame from a binary file object; raises CodecError on bad input.

    Reads to end of stream: the format is self-contained and length-checked,
    so any bytes after the frame are reported as trailing data.
    """
    try:
        data = fp.read()
    except UnicodeDecodeError as exc:
        raise CodecError("decode_stream requires a binary file object, got text") from exc
    if isinstance(data, str):
        raise CodecError("decode_stream requires a binary file object, got text")
    return decode(data)


def dump_text(data: bytes) -> str:
    """Render an encoded frame as human-readable text, one record per line.

    Each line lists all four fields as ``name=value`` pairs in schema order,
    e.g. ``ts=100 sensor_id=1 value=1.5 flags=0``. Floats use repr() so the
    text is exact (round-trippable) and NaN/inf are spelled out. The frame is
    fully validated first, so corrupted input raises CodecError rather than
    producing a misleading dump. Returns "" for an empty frame.
    """
    data = bytes(data) if isinstance(data, (bytearray, memoryview)) else data
    _, body_end = _check_frame(data)
    lines = [
        f"ts={ts} sensor_id={sid} value={value!r} flags={flags}"
        for ts, sid, value, flags in _RECORD.iter_unpack(data[_HEADER.size:body_end])
    ]
    return "".join(line + "\n" for line in lines)


def filter_sensor(data: bytes, sensor_id: int) -> bytes:
    """Return a new valid frame holding only the records for ``sensor_id``, in order.

    Works on the packed records directly (no dict materialization): matching
    15-byte records are copied verbatim under a fresh header and checksum.
    Raises CodecError if ``data`` is malformed and ValueError/TypeError if
    ``sensor_id`` is not a valid sensor id.
    """
    if isinstance(sensor_id, bool) or not isinstance(sensor_id, int):
        raise TypeError(f"sensor_id must be int, got {type(sensor_id).__name__}")
    lo, hi = _INT_RANGES["sensor_id"]
    if not lo <= sensor_id <= hi:
        raise ValueError(f"sensor_id={sensor_id} out of range {lo}..{hi}")

    data = bytes(data) if isinstance(data, (bytearray, memoryview)) else data
    _, body_end = _check_frame(data)

    kept = bytearray()
    size = _RECORD.size
    for off in range(_HEADER.size, body_end, size):
        if _RECORD.unpack_from(data, off)[1] == sensor_id:
            kept += data[off:off + size]

    out = bytearray(_HEADER.pack(MAGIC, VERSION, len(kept) // size))
    out += kept
    out += _TRAILER.pack(zlib.crc32(out) & 0xFFFFFFFF)
    return bytes(out)


def merge(a: bytes, b: bytes) -> bytes:
    """Merge two encoded frames into one valid frame sorted by ``ts``.

    The sort is stable: for equal ``ts``, records from ``a`` come before
    records from ``b``, and within each input the original order is kept.
    Neither input needs to be sorted already. Works on the packed 15-byte
    records directly (no dict materialization). Raises CodecError if either
    input is malformed.
    """
    a = bytes(a) if isinstance(a, (bytearray, memoryview)) else a
    b = bytes(b) if isinstance(b, (bytearray, memoryview)) else b
    _, a_end = _check_frame(a)
    _, b_end = _check_frame(b)

    size = _RECORD.size
    packed = [a[off:off + size] for off in range(_HEADER.size, a_end, size)]
    packed += [b[off:off + size] for off in range(_HEADER.size, b_end, size)]
    if len(packed) > 2**32 - 1:
        raise ValueError("too many records")

    # ts is the first field (little-endian u32); sorted() is stable, and the
    # records of ``a`` precede those of ``b`` in ``packed``.
    packed.sort(key=lambda rec: int.from_bytes(rec[:4], "little"))

    out = bytearray(_HEADER.pack(MAGIC, VERSION, len(packed)))
    out += b"".join(packed)
    out += _TRAILER.pack(zlib.crc32(out) & 0xFFFFFFFF)
    return bytes(out)
