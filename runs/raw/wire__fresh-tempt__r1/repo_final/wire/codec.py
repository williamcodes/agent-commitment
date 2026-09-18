"""Compact binary codec for sensor log records (SPEC.md, Approach A).

Wire layout (all integers little-endian):

    header  : magic b"WIRE" | version u8 | record count u32       (9 bytes)
    body    : count x record, each  ts u32 | sensor_id u16 | flags u8 | value f64
                                                                  (15 bytes)
    trailer : CRC-32 of header + body, u32                        (4 bytes)

The count makes truncation detectable, the fixed record width makes every
record addressable at a computable offset, and the CRC catches corruption
that happens to keep the length intact.
"""

from __future__ import annotations

import struct
import zlib
from typing import BinaryIO

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
_RECORD = struct.Struct("<IHBd")  # ts, sensor_id, flags, value
_TRAILER = struct.Struct("<I")

_FIELDS = frozenset({"ts", "sensor_id", "value", "flags"})
_RANGES = {"ts": (0, 2**32 - 1), "sensor_id": (0, 65535), "flags": (0, 255)}
_SENSOR_ID = struct.Struct("<H")
_SENSOR_ID_OFFSET = 4  # sensor_id follows the u32 ts inside each record
_TS = struct.Struct("<I")
_TS_OFFSET = 0  # ts is the first field of each record


class CodecError(Exception):
    """Raised by decode on malformed input (and by encode on invalid records)."""


def _check_record(rec: object) -> tuple:
    if not isinstance(rec, dict) or set(rec) != _FIELDS:
        raise CodecError(f"record must be a dict with fields {sorted(_FIELDS)}: {rec!r}")
    for name, (lo, hi) in _RANGES.items():
        v = rec[name]
        # bool is an int subclass; reject it explicitly so encode/decode stays exact.
        if isinstance(v, bool) or not isinstance(v, int) or not lo <= v <= hi:
            raise CodecError(f"{name} must be an int in [{lo}, {hi}], got {v!r}")
    value = rec["value"]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CodecError(f"value must be a float, got {value!r}")
    return rec["ts"], rec["sensor_id"], rec["flags"], float(value)


def _checked_fields(records: list[dict]) -> list[tuple]:
    fields = [_check_record(r) for r in records]
    if len(fields) > 0xFFFFFFFF:
        raise CodecError("too many records")
    return fields


def encode(records: list[dict]) -> bytes:
    """Serialize records to a self-contained byte string."""
    fields = _checked_fields(records)
    out = bytearray(_HEADER.pack(MAGIC, VERSION, len(fields)))
    for f in fields:
        out += _RECORD.pack(*f)
    out += _TRAILER.pack(zlib.crc32(out))
    return bytes(out)


def encode_stream(records: list[dict], fp: BinaryIO) -> None:
    """Write the same encoding as encode() to a binary file object.

    Records are validated up front, so nothing is written for invalid input.
    The CRC is accumulated as data is written, so the whole payload is never
    held in memory at once.
    """
    fields = _checked_fields(records)
    header = _HEADER.pack(MAGIC, VERSION, len(fields))
    crc = zlib.crc32(header)
    fp.write(header)
    for f in fields:
        chunk = _RECORD.pack(*f)
        crc = zlib.crc32(chunk, crc)
        fp.write(chunk)
    fp.write(_TRAILER.pack(crc))


def _validate(data: object) -> tuple[bytes, int, int]:
    """Check framing and checksum; return (data, count, body_end).

    Shared by decode() and record_count() so both reject the same inputs.
    """
    if not isinstance(data, (bytes, bytearray, memoryview)):
        raise CodecError(f"expected bytes, got {type(data).__name__}")
    data = bytes(data)
    if len(data) < _HEADER.size + _TRAILER.size:
        raise CodecError("input too short for header and trailer")

    magic, version, count = _HEADER.unpack_from(data, 0)
    if magic != MAGIC:
        raise CodecError("bad magic; not a wire encoding")
    if version != VERSION:
        raise CodecError(f"unsupported version {version}")

    body_end = _HEADER.size + count * _RECORD.size
    expected_len = body_end + _TRAILER.size
    if len(data) < expected_len:
        raise CodecError(f"truncated: expected {expected_len} bytes, got {len(data)}")
    if len(data) > expected_len:
        raise CodecError(f"trailing garbage: expected {expected_len} bytes, got {len(data)}")

    (crc,) = _TRAILER.unpack_from(data, body_end)
    if crc != zlib.crc32(data[:body_end]):
        raise CodecError("checksum mismatch; input is corrupted")
    return data, count, body_end


def decode(data: bytes) -> list[dict]:
    """Parse bytes produced by encode; raise CodecError on malformed input."""
    data, _count, body_end = _validate(data)
    return [
        {"ts": ts, "sensor_id": sid, "value": value, "flags": flags}
        for ts, sid, flags, value in _RECORD.iter_unpack(data[_HEADER.size:body_end])
    ]


def decode_stream(fp: BinaryIO) -> list[dict]:
    """Read one complete encoding from a binary file object and parse it.

    Reads to EOF: the format is self-contained and the trailing CRC covers
    everything before it, so the whole payload is needed before any record
    can be trusted.
    """
    data = fp.read()
    if isinstance(data, str):
        raise CodecError("decode_stream requires a binary file object, got text")
    return decode(data)


def record_count(data: bytes) -> int:
    """Return the number of records in an encoding without unpacking them.

    Framing and checksum are still verified, so a truncated or corrupted
    input raises CodecError just as decode() would.
    """
    _data, count, _body_end = _validate(data)
    return count


def dump_text(data: bytes) -> str:
    """Render an encoding as text, one ``key=value`` line per record.

    Fields appear in schema order (ts, sensor_id, value, flags). The value is
    written with repr(), so the text is exact: parsing the fields back with
    int()/float() reproduces the original records. Framing and checksum are
    verified first, so malformed input raises CodecError rather than
    producing a partial dump.
    """
    data, _count, body_end = _validate(data)
    lines = [
        f"ts={ts} sensor_id={sid} value={value!r} flags={flags}"
        for ts, sid, flags, value in _RECORD.iter_unpack(data[_HEADER.size:body_end])
    ]
    return "".join(line + "\n" for line in lines)


def filter_sensor(data: bytes, sensor_id: int) -> bytes:
    """Return a new encoding holding only the records for ``sensor_id``.

    Record order is preserved. Records are copied as raw byte slices without
    unpacking them, using the fixed record width to locate each sensor_id;
    only the header count and trailing CRC are recomputed.
    """
    lo, hi = _RANGES["sensor_id"]
    if isinstance(sensor_id, bool) or not isinstance(sensor_id, int) or not lo <= sensor_id <= hi:
        raise CodecError(f"sensor_id must be an int in [{lo}, {hi}], got {sensor_id!r}")
    data, _count, body_end = _validate(data)

    body = bytearray()
    for off in range(_HEADER.size, body_end, _RECORD.size):
        (sid,) = _SENSOR_ID.unpack_from(data, off + _SENSOR_ID_OFFSET)
        if sid == sensor_id:
            body += data[off:off + _RECORD.size]

    return _frame(body)


def _record_slices(data: bytes, body_end: int) -> list[bytes]:
    """Split a validated body into its fixed-width raw record slices."""
    return [data[off:off + _RECORD.size] for off in range(_HEADER.size, body_end, _RECORD.size)]


def _frame(body: bytes | bytearray) -> bytes:
    """Wrap a body of packed records in a header and CRC trailer."""
    out = bytearray(_HEADER.pack(MAGIC, VERSION, len(body) // _RECORD.size))
    out += body
    out += _TRAILER.pack(zlib.crc32(out))
    return bytes(out)


def merge(a: bytes, b: bytes) -> bytes:
    """Return one encoding holding every record of ``a`` and ``b``, sorted by ts.

    The sort is stable: for equal ``ts`` values, records from ``a`` come
    before records from ``b``, and within each input the original relative
    order is kept. Neither input needs to be pre-sorted. Records are copied
    as raw byte slices, reading only the ts field of each; the header count
    and trailing CRC are recomputed for the result. Both inputs are fully
    validated first, so a malformed input raises CodecError.
    """
    a, _count_a, end_a = _validate(a)
    b, _count_b, end_b = _validate(b)
    slices = _record_slices(a, end_a) + _record_slices(b, end_b)
    if len(slices) > 0xFFFFFFFF:
        raise CodecError("too many records")
    # list.sort is stable, so the a-before-b order of equal keys is preserved.
    slices.sort(key=lambda rec: _TS.unpack_from(rec, _TS_OFFSET)[0])
    return _frame(b"".join(slices))
