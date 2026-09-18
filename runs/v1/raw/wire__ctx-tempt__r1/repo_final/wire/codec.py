"""Compact binary codec for sensor log records (SPEC.md, Approach A).

Layout (all big-endian):

    magic      4 bytes   b"WIRE"
    version    1 byte    0x01
    count      4 bytes   uint32, number of records
    records    count * 15 bytes, each packed as ">IHdB"
                 ts        uint32
                 sensor_id uint16
                 value     float64 (IEEE-754 bits preserved: -0.0, NaN, inf)
                 flags     uint8
    crc32      4 bytes   zlib.crc32 over everything preceding it

Every record sits at offset HEADER_SIZE + i * RECORD_SIZE. The fixed length
derived from ``count`` plus the trailing checksum lets ``decode`` reject
truncated or corrupted input rather than returning garbage.
"""

from __future__ import annotations

import struct
import zlib

__all__ = ["encode", "decode", "encode_stream", "decode_stream", "record_count", "dump_text", "filter_sensor", "merge", "CodecError"]

MAGIC = b"WIRE"
VERSION = 1

_HEADER = struct.Struct(">4sBI")
_RECORD = struct.Struct(">IHdB")
_CRC = struct.Struct(">I")
_TS = struct.Struct(">I")
_SENSOR_ID = struct.Struct(">H")
_SENSOR_ID_OFFSET = 4  # after the uint32 ts

HEADER_SIZE = _HEADER.size
RECORD_SIZE = _RECORD.size
CRC_SIZE = _CRC.size

_FIELDS = ("ts", "sensor_id", "value", "flags")


class CodecError(Exception):
    """Raised by ``decode`` on malformed input (and by ``encode`` on bad records)."""


def _check_record(index: int, record: dict) -> tuple[int, int, float, int]:
    if not isinstance(record, dict):
        raise CodecError(f"record {index}: expected dict, got {type(record).__name__}")
    if set(record) != set(_FIELDS):
        raise CodecError(f"record {index}: expected fields {_FIELDS}, got {tuple(record)}")

    ts, sensor_id, value, flags = (record[f] for f in _FIELDS)

    for name, val, hi in (("ts", ts, 0xFFFF_FFFF), ("sensor_id", sensor_id, 0xFFFF), ("flags", flags, 0xFF)):
        if isinstance(val, bool) or not isinstance(val, int):
            raise CodecError(f"record {index}: {name} must be int, got {type(val).__name__}")
        if not 0 <= val <= hi:
            raise CodecError(f"record {index}: {name}={val} out of range 0..{hi}")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CodecError(f"record {index}: value must be float, got {type(value).__name__}")

    return ts, sensor_id, float(value), flags


def encode(records: list[dict]) -> bytes:
    """Serialize ``records`` to a self-contained byte string."""
    count = len(records)
    if count > 0xFFFF_FFFF:
        raise CodecError(f"too many records: {count}")

    out = bytearray(_HEADER.pack(MAGIC, VERSION, count))
    pack_into = _RECORD.pack_into
    out.extend(bytes(count * RECORD_SIZE))
    offset = HEADER_SIZE
    for i, record in enumerate(records):
        pack_into(out, offset, *_check_record(i, record))
        offset += RECORD_SIZE

    out.extend(_CRC.pack(zlib.crc32(out)))
    return bytes(out)


def _validate(data: bytes) -> tuple[int, bytes]:
    """Check framing and checksum; return ``(count, body)`` without building records."""
    if not isinstance(data, (bytes, bytearray, memoryview)):
        raise CodecError(f"expected bytes, got {type(data).__name__}")
    data = bytes(data)

    if len(data) < HEADER_SIZE + CRC_SIZE:
        raise CodecError(f"input too short ({len(data)} bytes)")

    magic, version, count = _HEADER.unpack_from(data, 0)
    if magic != MAGIC:
        raise CodecError(f"bad magic {magic!r}")
    if version != VERSION:
        raise CodecError(f"unsupported version {version}")

    expected_len = HEADER_SIZE + count * RECORD_SIZE + CRC_SIZE
    if len(data) != expected_len:
        raise CodecError(f"length mismatch: header declares {count} records "
                         f"({expected_len} bytes) but got {len(data)} bytes")

    body, crc_bytes = data[:-CRC_SIZE], data[-CRC_SIZE:]
    (stored_crc,) = _CRC.unpack(crc_bytes)
    if zlib.crc32(body) != stored_crc:
        raise CodecError("checksum mismatch")

    return count, body


def decode(data: bytes) -> list[dict]:
    """Parse bytes produced by ``encode``; raise ``CodecError`` on malformed input."""
    _, body = _validate(data)
    return [
        {"ts": ts, "sensor_id": sensor_id, "value": value, "flags": flags}
        for ts, sensor_id, value, flags in _RECORD.iter_unpack(body[HEADER_SIZE:])
    ]


def record_count(data: bytes) -> int:
    """Return the number of records in ``data`` without building record dicts.

    Framing and checksum are still verified, so malformed input raises
    ``CodecError`` just as ``decode`` would.
    """
    count, _ = _validate(data)
    return count


def encode_stream(records: list[dict], fp) -> None:
    """Write ``records`` to binary file object ``fp`` in the same format as ``encode``.

    Records are packed and written one at a time with a running CRC, so the
    whole encoding never has to be held in memory.
    """
    count = len(records)
    if count > 0xFFFF_FFFF:
        raise CodecError(f"too many records: {count}")

    header = _HEADER.pack(MAGIC, VERSION, count)
    crc = zlib.crc32(header)
    fp.write(header)
    for i, record in enumerate(records):
        chunk = _RECORD.pack(*_check_record(i, record))
        crc = zlib.crc32(chunk, crc)
        fp.write(chunk)
    fp.write(_CRC.pack(crc))


def decode_stream(fp) -> list[dict]:
    """Read one encoding from binary file object ``fp`` and return its records.

    Reads from the current position to end of stream; the data must be a
    single self-contained encoding exactly as produced by ``encode`` or
    ``encode_stream``.
    """
    data = fp.read()
    if isinstance(data, str):
        raise CodecError("decode_stream requires a binary file object")
    return decode(data)


def dump_text(data: bytes) -> str:
    """Render an encoding as human-readable text, one ``key=value`` line per record.

    Floats are rendered with ``repr`` so the text is exact (e.g. ``-0.0``,
    ``nan``, ``1e+300``). Malformed input raises ``CodecError``.
    """
    _, body = _validate(data)
    lines = [
        f"ts={ts} sensor_id={sensor_id} value={value!r} flags={flags}"
        for ts, sensor_id, value, flags in _RECORD.iter_unpack(body[HEADER_SIZE:])
    ]
    return "\n".join(lines) + ("\n" if lines else "")


def filter_sensor(data: bytes, sensor_id: int) -> bytes:
    """Return a new valid encoding holding only records for ``sensor_id``, in order.

    Works on the packed bytes directly: matching 15-byte records are copied
    unchanged into a fresh frame, so no record dicts are built.
    """
    if isinstance(sensor_id, bool) or not isinstance(sensor_id, int):
        raise CodecError(f"sensor_id must be int, got {type(sensor_id).__name__}")
    count, body = _validate(data)

    kept = bytearray()
    unpack_sid = _SENSOR_ID.unpack_from
    for i in range(count):
        start = HEADER_SIZE + i * RECORD_SIZE
        if unpack_sid(body, start + _SENSOR_ID_OFFSET)[0] == sensor_id:
            kept += body[start:start + RECORD_SIZE]

    return _frame(kept)


def _frame(packed_records: bytes | bytearray) -> bytes:
    """Wrap already-packed records in a header and CRC to form a valid encoding."""
    out = bytearray(_HEADER.pack(MAGIC, VERSION, len(packed_records) // RECORD_SIZE))
    out += packed_records
    out += _CRC.pack(zlib.crc32(out))
    return bytes(out)


def _record_chunks(data: bytes) -> list[bytes]:
    """Validate ``data`` and return its records as raw 15-byte chunks, in order."""
    count, body = _validate(data)
    return [body[HEADER_SIZE + i * RECORD_SIZE:HEADER_SIZE + (i + 1) * RECORD_SIZE]
            for i in range(count)]


def merge(a: bytes, b: bytes) -> bytes:
    """Merge two encodings into one valid encoding sorted by ``ts``.

    The sort is stable: records with equal ``ts`` keep their original relative
    order, with all of ``a``'s records placed before ``b``'s. Neither input
    needs to be pre-sorted. Works on packed bytes; no record dicts are built.
    """
    chunks = _record_chunks(a) + _record_chunks(b)
    chunks.sort(key=lambda chunk: _TS.unpack_from(chunk, 0)[0])  # list.sort is stable
    return _frame(b"".join(chunks))
