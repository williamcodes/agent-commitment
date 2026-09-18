"""Approach B: JSON lines. UTF-8 text; first line is a header object carrying the record count,
then one JSON object per line."""
from __future__ import annotations
import json
from typing import BinaryIO

FIELDS = ("ts", "sensor_id", "value", "flags")
FORMAT = "wire-jsonl"
VERSION = 1


class CodecError(Exception):
    pass


def _header_line(count: int) -> str:
    return json.dumps({"format": FORMAT, "version": VERSION, "count": count})


def _record_line(r: dict) -> str:
    if set(r) != set(FIELDS):
        raise ValueError("record must have exactly fields %r" % (FIELDS,))
    return json.dumps({k: r[k] for k in FIELDS})


def _split(data: bytes) -> tuple[int, list[str]]:
    """Return (declared count, record lines). Raises CodecError on any malformed input."""
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


# ---- T1 --------------------------------------------------------------------------------
def encode(records: list[dict]) -> bytes:
    lines = [_header_line(len(records))] + [_record_line(r) for r in records]
    return ("\n".join(lines) + "\n").encode("utf-8")


def decode(data: bytes) -> list[dict]:
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
    count, _ = _split(data)     # counts lines; does not parse record objects
    return count


# ---- T3 --------------------------------------------------------------------------------
def dump_text(data: bytes) -> str:
    # the body already is the human-readable dump; just drop the header line
    _, lines = _split(data)
    return "\n".join(lines) + ("\n" if lines else "")


def filter_sensor(data: bytes, sensor_id: int) -> bytes:
    kept = [r for r in decode(data) if r["sensor_id"] == sensor_id]
    return encode(kept)


# ---- T4 --------------------------------------------------------------------------------
def merge(a: bytes, b: bytes) -> bytes:
    combined = decode(a) + decode(b)
    combined.sort(key=lambda r: r["ts"])     # stable: a's records precede b's on ties
    return encode(combined)
