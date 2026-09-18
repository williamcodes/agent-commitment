"""Approach A: compact fixed-width binary records behind a small header.

Layout (all little-endian):
    header: magic b"WIRE" | version u8 | record count u32       -> 9 bytes
    record: ts u32 | sensor_id u16 | value f64 | flags u8      -> 15 bytes
"""
from __future__ import annotations
import struct
from typing import BinaryIO

MAGIC = b"WIRE"
VERSION = 1
_HEADER = struct.Struct("<4sBI")
_RECORD = struct.Struct("<IHdB")
HEADER_SIZE = _HEADER.size
RECORD_SIZE = _RECORD.size
FIELDS = ("ts", "sensor_id", "value", "flags")


class CodecError(Exception):
    pass


def _pack_record(r: dict) -> bytes:
    try:
        return _RECORD.pack(r["ts"], r["sensor_id"], r["value"], r["flags"])
    except (KeyError, struct.error, TypeError) as e:
        raise ValueError("invalid record %r: %s" % (r, e)) from e


def _unpack_record(chunk: bytes) -> dict:
    ts, sensor_id, value, flags = _RECORD.unpack(chunk)
    return {"ts": ts, "sensor_id": sensor_id, "value": value, "flags": flags}


def _parse_header(data: bytes) -> int:
    if len(data) < HEADER_SIZE:
        raise CodecError("truncated header")
    magic, version, count = _HEADER.unpack_from(data)
    if magic != MAGIC:
        raise CodecError("bad magic")
    if version != VERSION:
        raise CodecError("unsupported version %d" % version)
    return count


def _check_body(data: bytes, count: int) -> None:
    expected = HEADER_SIZE + count * RECORD_SIZE
    if len(data) != expected:
        raise CodecError("expected %d bytes, got %d" % (expected, len(data)))


# ---- T1 --------------------------------------------------------------------------------
def encode(records: list[dict]) -> bytes:
    return _HEADER.pack(MAGIC, VERSION, len(records)) + b"".join(_pack_record(r) for r in records)


def decode(data: bytes) -> list[dict]:
    data = bytes(data)
    count = _parse_header(data)
    _check_body(data, count)
    return [_unpack_record(chunk) for chunk in _record_chunks(data, count)]


def _record_chunks(data: bytes, count: int):
    for i in range(count):
        start = HEADER_SIZE + i * RECORD_SIZE
        yield data[start:start + RECORD_SIZE]


# ---- T2 --------------------------------------------------------------------------------
def encode_stream(records: list[dict], fp: BinaryIO) -> None:
    fp.write(_HEADER.pack(MAGIC, VERSION, len(records)))
    for r in records:
        fp.write(_pack_record(r))


def decode_stream(fp: BinaryIO) -> list[dict]:
    return decode(fp.read())


def record_count(data: bytes) -> int:
    data = bytes(data)
    count = _parse_header(data)
    _check_body(data, count)
    return count


# ---- T3 --------------------------------------------------------------------------------
def dump_text(data: bytes) -> str:
    lines = []
    for r in decode(data):
        lines.append("ts=%d sensor_id=%d value=%r flags=%d" % (r["ts"], r["sensor_id"], r["value"], r["flags"]))
    return "\n".join(lines) + ("\n" if lines else "")


def filter_sensor(data: bytes, sensor_id: int) -> bytes:
    data = bytes(data)
    count = _parse_header(data)
    _check_body(data, count)
    # no full decode needed: sensor_id lives at a fixed offset within each fixed-width slice
    kept = [chunk for chunk in _record_chunks(data, count)
            if struct.unpack_from("<H", chunk, 4)[0] == sensor_id]
    return _HEADER.pack(MAGIC, VERSION, len(kept)) + b"".join(kept)


# ---- T4 --------------------------------------------------------------------------------
def merge(a: bytes, b: bytes) -> bytes:
    a, b = bytes(a), bytes(b)
    ca, cb = _parse_header(a), _parse_header(b)
    _check_body(a, ca)
    _check_body(b, cb)
    chunks_a = list(_record_chunks(a, ca))
    chunks_b = list(_record_chunks(b, cb))
    ts = lambda chunk: struct.unpack_from("<I", chunk, 0)[0]
    out = []
    i = j = 0
    while i < len(chunks_a) and j < len(chunks_b):
        if ts(chunks_b[j]) < ts(chunks_a[i]):
            out.append(chunks_b[j]); j += 1
        else:
            out.append(chunks_a[i]); i += 1
    out.extend(chunks_a[i:])
    out.extend(chunks_b[j:])
    # inputs are not guaranteed sorted; a stable sort keeps a-before-b for equal ts
    out.sort(key=ts)
    return _HEADER.pack(MAGIC, VERSION, len(out)) + b"".join(out)
