"""Compact binary codec for sensor log records (Approach A).

Layout (all little-endian):

    header  : magic b"WIRE" | version u8 | record count u32
    body    : count x record, each ``<IHdB`` (ts u32, sensor_id u16, value f64, flags u8)
    trailer : CRC-32 u32 over header + body

Every record sits at a computable offset (HEADER_SIZE + i * RECORD_SIZE).
The count and trailing checksum let ``decode`` reject truncated or corrupted
input rather than returning garbage.
"""

from __future__ import annotations

import struct
import zlib
from typing import BinaryIO, Iterable

__all__ = ["encode", "decode", "encode_stream", "decode_stream", "record_count", "dump_text", "filter_sensor", "merge", "CodecError"]

MAGIC = b"WIRE"
VERSION = 1

_HEADER = struct.Struct("<4sBI")
_RECORD = struct.Struct("<IHdB")
_TRAILER = struct.Struct("<I")
_TS = struct.Struct("<I")  # ts field, at offset 0 within a record
_SENSOR_ID = struct.Struct("<H")  # sensor_id field, at offset 4 within a record

HEADER_SIZE = _HEADER.size
RECORD_SIZE = _RECORD.size
TRAILER_SIZE = _TRAILER.size

_FIELDS = ("ts", "sensor_id", "value", "flags")


class CodecError(Exception):
    """Raised by ``decode`` on malformed input."""


def _validate(record: dict, index: int) -> tuple[int, int, float, int]:
    if not isinstance(record, dict):
        raise TypeError(f"record {index}: expected dict, got {type(record).__name__}")
    if set(record) != set(_FIELDS):
        raise ValueError(f"record {index}: expected fields {_FIELDS}, got {tuple(record)}")

    ts, sensor_id, value, flags = (record[f] for f in _FIELDS)
    for name, val, hi in (("ts", ts, 0xFFFF_FFFF), ("sensor_id", sensor_id, 0xFFFF), ("flags", flags, 0xFF)):
        if isinstance(val, bool) or not isinstance(val, int):
            raise TypeError(f"record {index}: {name} must be int")
        if not 0 <= val <= hi:
            raise ValueError(f"record {index}: {name}={val} out of range 0..{hi}")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"record {index}: value must be float")
    return ts, sensor_id, float(value), flags


def encode(records: list[dict]) -> bytes:
    """Serialize ``records`` to a self-contained byte string."""
    out = bytearray(_HEADER.pack(MAGIC, VERSION, len(records)))
    for i, rec in enumerate(records):
        out += _RECORD.pack(*_validate(rec, i))
    out += _TRAILER.pack(zlib.crc32(out))
    return bytes(out)


def encode_stream(records: Iterable[dict], fp: BinaryIO) -> None:
    """Write ``records`` to binary file object ``fp`` in the same format as ``encode``.

    Records are written incrementally with a running CRC, so the whole body is
    never buffered. ``records`` must be sized (the count lives in the header).
    """
    records = list(records) if not hasattr(records, "__len__") else records
    header = _HEADER.pack(MAGIC, VERSION, len(records))
    crc = zlib.crc32(header)
    fp.write(header)
    for i, rec in enumerate(records):
        chunk = _RECORD.pack(*_validate(rec, i))
        crc = zlib.crc32(chunk, crc)
        fp.write(chunk)
    fp.write(_TRAILER.pack(crc))


def _read_exact(fp: BinaryIO, n: int, what: str) -> bytes:
    chunk = fp.read(n)
    if chunk is None or len(chunk) != n:
        raise CodecError(f"truncated input while reading {what}")
    return chunk


def _parse_header(header: bytes) -> int:
    """Validate a raw header and return the declared record count."""
    if len(header) < HEADER_SIZE:
        raise CodecError("input too short to contain a header")
    magic, version, count = _HEADER.unpack_from(header, 0)
    if magic != MAGIC:
        raise CodecError("bad magic; not a wire encoding")
    if version != VERSION:
        raise CodecError(f"unsupported version {version}")
    return count


def _check_frame(data: bytes) -> int:
    """Validate framing (header, total length, checksum); return record count."""
    if not isinstance(data, (bytes, bytearray, memoryview)):
        raise CodecError(f"expected bytes, got {type(data).__name__}")
    data = bytes(data)
    if len(data) < HEADER_SIZE + TRAILER_SIZE:
        raise CodecError("input too short to contain a header")
    count = _parse_header(data)

    expected_len = HEADER_SIZE + count * RECORD_SIZE + TRAILER_SIZE
    if len(data) != expected_len:
        raise CodecError(f"length mismatch: expected {expected_len} bytes, got {len(data)}")

    body_end = expected_len - TRAILER_SIZE
    (stored_crc,) = _TRAILER.unpack_from(data, body_end)
    if stored_crc != zlib.crc32(data[:body_end]):
        raise CodecError("checksum mismatch; data is corrupted")
    return count


def _unpack_records(body: bytes, count: int) -> list[dict]:
    return [dict(zip(_FIELDS, rec)) for rec in _RECORD.iter_unpack(body[: count * RECORD_SIZE])]


def record_count(data: bytes) -> int:
    """Return the number of records in ``data`` without building record dicts.

    The framing (magic, version, length, checksum) is still verified, so
    malformed input raises ``CodecError`` just as ``decode`` would.
    """
    return _check_frame(data)


def decode(data: bytes) -> list[dict]:
    """Parse bytes produced by ``encode``; raise ``CodecError`` if malformed."""
    count = _check_frame(data)
    data = bytes(data)
    return _unpack_records(data[HEADER_SIZE:], count)


def decode_stream(fp: BinaryIO) -> list[dict]:
    """Read one encoding from binary file object ``fp``; raise ``CodecError`` if malformed.

    Reads exactly the bytes belonging to the encoding, so ``fp`` is left
    positioned just after the trailer.
    """
    header = fp.read(HEADER_SIZE)
    if header is None or len(header) != HEADER_SIZE:
        raise CodecError("truncated input while reading header")
    count = _parse_header(header)
    crc = zlib.crc32(header)

    body = _read_exact(fp, count * RECORD_SIZE, "records")
    crc = zlib.crc32(body, crc)

    (stored_crc,) = _TRAILER.unpack(_read_exact(fp, TRAILER_SIZE, "checksum"))
    if stored_crc != crc:
        raise CodecError("checksum mismatch; data is corrupted")
    return _unpack_records(body, count)


def dump_text(data: bytes) -> str:
    """Render an encoding as human-readable text, one ``key=value`` line per record.

    Floats use ``repr`` so the shortest exact representation is shown.
    Returns an empty string for an empty encoding.
    """
    lines = [
        f"ts={ts} sensor_id={sensor_id} value={value!r} flags={flags}"
        for ts, sensor_id, value, flags in _RECORD.iter_unpack(_body(data))
    ]
    return "".join(line + "\n" for line in lines)


def filter_sensor(data: bytes, sensor_id: int) -> bytes:
    """Return a valid encoding holding only records for ``sensor_id``, in original order.

    Records are copied as packed bytes; only the sensor_id field is inspected.
    """
    body = _body(data)
    kept = [
        body[off : off + RECORD_SIZE]
        for off in range(0, len(body), RECORD_SIZE)
        if _SENSOR_ID.unpack_from(body, off + 4)[0] == sensor_id
    ]
    return _frame(kept)


def merge(a: bytes, b: bytes) -> bytes:
    """Merge two encodings into one, sorted by ``ts``.

    The sort is stable: for equal ``ts``, records from ``a`` precede those from ``b``,
    and each input's internal order is preserved. Records are moved as packed bytes.
    """
    records = _records(_body(a)) + _records(_body(b))
    records.sort(key=lambda rec: _TS.unpack_from(rec, 0)[0])
    return _frame(records)


def _records(body: bytes) -> list[bytes]:
    """Split packed record bytes into one slice per record."""
    return [body[off : off + RECORD_SIZE] for off in range(0, len(body), RECORD_SIZE)]


def _frame(packed_records: list[bytes]) -> bytes:
    """Wrap already-packed records in a header and CRC-32 trailer."""
    out = bytearray(_HEADER.pack(MAGIC, VERSION, len(packed_records)))
    out += b"".join(packed_records)
    out += _TRAILER.pack(zlib.crc32(out))
    return bytes(out)


def _body(data: bytes) -> bytes:
    """Validate framing and return just the packed record bytes."""
    count = _check_frame(data)
    return bytes(data)[HEADER_SIZE : HEADER_SIZE + count * RECORD_SIZE]
