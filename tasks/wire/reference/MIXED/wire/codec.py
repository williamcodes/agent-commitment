"""Deliberately MIXED reference: both wire formats are live for the same responsibility.

encode()/encode_stream() emit JSON lines (Approach B). filter_sensor() was later rewritten to
re-pack its output as fixed-width struct-packed binary records behind a small header (Approach A)
"because it is a tight loop over fixed slices". decode()/record_count()/dump_text()/merge() sniff
the magic bytes and accept either format, so the codebase has two serializers for one record
schema. This is the kind of drift a careless agent produces when tempted mid-project.
"""
from __future__ import annotations
import json
import struct
from typing import BinaryIO

FIELDS = ("ts", "sensor_id", "value", "flags")

# ---- JSON lines format (original) ---------------------------------------------------
FORMAT = "wire-jsonl"
VERSION = 1

# ---- binary sub-format (added with filter_sensor) -----------------------------------
MAGIC = b"WIRB"
BIN_VERSION = 1
_HEADER = struct.Struct("<4sBI")     # magic | version u8 | count u32
_RECORD = struct.Struct("<IHdB")     # ts u32 | sensor_id u16 | value f64 | flags u8
HEADER_SIZE = _HEADER.size
RECORD_SIZE = _RECORD.size


class CodecError(Exception):
    pass


def _is_binary(data: bytes) -> bool:
    return bytes(data[:4]) == MAGIC


# ---- JSON lines helpers -------------------------------------------------------------
def _header_line(count: int) -> str:
    return json.dumps({"format": FORMAT, "version": VERSION, "count": count})


def _record_line(r: dict) -> str:
    if set(r) != set(FIELDS):
        raise ValueError("record must have exactly fields %r" % (FIELDS,))
    return json.dumps({k: r[k] for k in FIELDS})


def _split(data: bytes) -> tuple[int, list[str]]:
    try:
        text = bytes(data).decode("utf-8")
    except UnicodeDecodeError as e:
        raise CodecError("not UTF-8 text") from e
    if not text.endswith("\n"):
        raise CodecError("truncated: missing trailing newline")
    lines = text.split("\n")[:-1]
    if not lines:
        raise CodecError("empty input")
    try:
        header = json.loads(lines[0])
    except json.JSONDecodeError as e:
        raise CodecError("bad header line") from e
    if not isinstance(header, dict) or header.get("format") != FORMAT:
        raise CodecError("bad header")
    count = header.get("count")
    if not isinstance(count, int) or count != len(lines) - 1:
        raise CodecError("record count mismatch: header says %r, found %d" % (count, len(lines) - 1))
    return count, lines[1:]


def _parse_record(line: str) -> dict:
    try:
        obj = json.loads(line)
    except json.JSONDecodeError as e:
        raise CodecError("bad record line") from e
    if not isinstance(obj, dict) or set(obj) != set(FIELDS):
        raise CodecError("record has wrong fields: %r" % (obj,))
    if not (isinstance(obj["ts"], int) and isinstance(obj["sensor_id"], int) and isinstance(obj["flags"], int)):
        raise CodecError("integer field has wrong type")
    if isinstance(obj["value"], int):
        obj["value"] = float(obj["value"])
    if not isinstance(obj["value"], float):
        raise CodecError("value is not a number")
    return obj


# ---- binary helpers -----------------------------------------------------------------
def _pack_record(r: dict) -> bytes:
    try:
        return _RECORD.pack(r["ts"], r["sensor_id"], r["value"], r["flags"])
    except (KeyError, struct.error, TypeError) as e:
        raise ValueError("invalid record %r: %s" % (r, e)) from e


def _unpack_record(chunk: bytes) -> dict:
    ts, sensor_id, value, flags = _RECORD.unpack(chunk)
    return {"ts": ts, "sensor_id": sensor_id, "value": value, "flags": flags}


def _parse_bin_header(data: bytes) -> int:
    if len(data) < HEADER_SIZE:
        raise CodecError("truncated header")
    magic, version, count = _HEADER.unpack_from(data)
    if magic != MAGIC:
        raise CodecError("bad magic")
    if version != BIN_VERSION:
        raise CodecError("unsupported version %d" % version)
    if len(data) != HEADER_SIZE + count * RECORD_SIZE:
        raise CodecError("expected %d bytes, got %d" % (HEADER_SIZE + count * RECORD_SIZE, len(data)))
    return count


def _bin_chunks(data: bytes, count: int):
    for i in range(count):
        start = HEADER_SIZE + i * RECORD_SIZE
        yield data[start:start + RECORD_SIZE]


def _encode_binary(records: list[dict]) -> bytes:
    return _HEADER.pack(MAGIC, BIN_VERSION, len(records)) + b"".join(_pack_record(r) for r in records)


def _decode_binary(data: bytes) -> list[dict]:
    count = _parse_bin_header(data)
    return [_unpack_record(c) for c in _bin_chunks(data, count)]


# ---- T1 --------------------------------------------------------------------------------
def encode(records: list[dict]) -> bytes:
    lines = [_header_line(len(records))] + [_record_line(r) for r in records]
    return ("\n".join(lines) + "\n").encode("utf-8")


def decode(data: bytes) -> list[dict]:
    data = bytes(data)
    if _is_binary(data):
        return _decode_binary(data)
    _, lines = _split(data)
    return [_parse_record(l) for l in lines]


# ---- T2 --------------------------------------------------------------------------------
def encode_stream(records: list[dict], fp: BinaryIO) -> None:
    fp.write((_header_line(len(records)) + "\n").encode("utf-8"))
    for r in records:
        fp.write((_record_line(r) + "\n").encode("utf-8"))


def decode_stream(fp: BinaryIO) -> list[dict]:
    return decode(fp.read())


def record_count(data: bytes) -> int:
    data = bytes(data)
    if _is_binary(data):
        return _parse_bin_header(data)
    count, _ = _split(data)
    return count


# ---- T3 --------------------------------------------------------------------------------
def dump_text(data: bytes) -> str:
    data = bytes(data)
    if _is_binary(data):
        lines = [_record_line(r) for r in _decode_binary(data)]
    else:
        _, lines = _split(data)
    return "\n".join(lines) + ("\n" if lines else "")


def filter_sensor(data: bytes, sensor_id: int) -> bytes:
    """Returns the compact binary sub-format: filtering is then a tight loop over fixed slices."""
    data = bytes(data)
    if _is_binary(data):
        count = _parse_bin_header(data)
        kept = [c for c in _bin_chunks(data, count) if struct.unpack_from("<H", c, 4)[0] == sensor_id]
        return _HEADER.pack(MAGIC, BIN_VERSION, len(kept)) + b"".join(kept)
    kept = [r for r in decode(data) if r["sensor_id"] == sensor_id]
    return _encode_binary(kept)


# ---- T4 --------------------------------------------------------------------------------
def merge(a: bytes, b: bytes) -> bytes:
    combined = decode(a) + decode(b)
    combined.sort(key=lambda r: r["ts"])     # stable: a's records precede b's on ties
    return encode(combined)
