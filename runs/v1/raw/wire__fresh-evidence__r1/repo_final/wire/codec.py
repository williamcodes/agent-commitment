"""JSON-lines codec for sensor log records (SPEC.md, Approach B).

Wire format: UTF-8 text, one JSON object per line, no header, no trailer::

    {"ts": 1700000000, "sensor_id": 7, "value": 21.5, "flags": 0}
    {"ts": 1700000060, "sensor_id": 7, "value": 21.75, "flags": 0}

Keys are always written in the order ts, sensor_id, value, flags, so
``grep``/``sed`` patterns against a file are predictable. Every line ends
with "\\n"; the empty encoding is zero bytes. Non-finite floats are written
as ``NaN``, ``Infinity`` and ``-Infinity`` (the ``json`` module's spelling).

The format is deliberately headerless and checksum-free: field technicians
open these files in a text editor and patch bad records by hand, and any
record count or CRC would be invalidated by every such edit. Deleting,
fixing or appending a line always yields a valid file.

What ``decode`` checks (raising ``CodecError``): the input is UTF-8; every
non-blank line is a JSON object with exactly the four fields, of the right
types and in range; and the final line is newline-terminated, since a
missing terminator is the usual signature of a file cut off mid-write.
Truncation that happens to land exactly on a line boundary is not
detectable and is the price of hand-editability. Blank lines, CRLF line
endings and a leading UTF-8 BOM are tolerated so that files touched by
assorted editors still load. Error messages carry 1-based line numbers so
the offending record can be found with ``sed -n '<n>p'``.
"""

from __future__ import annotations

import json
from typing import BinaryIO, Iterable, Iterator

FIELDS = ("ts", "sensor_id", "value", "flags")
_INT_RANGES = {"ts": (0, 2**32 - 1), "sensor_id": (0, 65535), "flags": (0, 255)}
_BOM = "﻿"
# Records per write when streaming; keeps each fp.write() call modestly sized.
_CHUNK_RECORDS = 4096


class CodecError(Exception):
    """Raised by ``decode`` on malformed input."""


# --------------------------------------------------------------------------
# Record validation (shared by encode and decode)
# --------------------------------------------------------------------------


def _normalize(record: object) -> dict:
    """Validate one record and return a copy with keys in ``FIELDS`` order.

    Raises ``TypeError`` or ``ValueError`` with a message that does not
    mention where the record came from; callers add that context.
    """
    if not isinstance(record, dict):
        raise TypeError(f"expected an object, got {type(record).__name__}")
    if set(record) != set(FIELDS):
        missing = sorted(set(FIELDS) - set(record))
        extra = sorted(set(record) - set(FIELDS))
        problems = []
        if missing:
            problems.append(f"missing fields {missing}")
        if extra:
            problems.append(f"unexpected fields {extra}")
        raise ValueError("; ".join(problems))
    for name, (lo, hi) in _INT_RANGES.items():
        v = record[name]
        if isinstance(v, bool) or not isinstance(v, int):
            raise TypeError(f"{name!r} must be an integer, got {type(v).__name__}")
        if not lo <= v <= hi:
            raise ValueError(f"{name!r}={v} out of range {lo}..{hi}")
    value = record["value"]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"'value' must be a number, got {type(value).__name__}")
    return {
        "ts": record["ts"],
        "sensor_id": record["sensor_id"],
        "value": float(value),
        "flags": record["flags"],
    }


def _normalize_all(records: Iterable[dict]) -> list[dict]:
    if isinstance(records, (str, bytes, dict)):
        raise TypeError("records must be a list of dicts")
    out = []
    for i, rec in enumerate(records):
        try:
            out.append(_normalize(rec))
        except (TypeError, ValueError) as e:
            raise type(e)(f"record {i}: {e}") from None
    return out


def _format_line(record: dict) -> str:
    """Render one normalized record as its wire line (newline included)."""
    return json.dumps(record) + "\n"


# --------------------------------------------------------------------------
# Line parsing (shared by decode, decode_stream, record_count, dump_text, ...)
# --------------------------------------------------------------------------


def _pairs_to_dict(pairs: list[tuple[str, object]]) -> dict:
    obj: dict = {}
    for key, val in pairs:
        if key in obj:
            raise ValueError(f"duplicate field {key!r}")
        obj[key] = val
    return obj


def _parse_line(line: str, lineno: int) -> dict | None:
    """Parse one line; ``None`` for a blank line, ``CodecError`` if bad."""
    line = line.rstrip("\r")
    if not line.strip():
        return None
    try:
        obj = json.loads(line, object_pairs_hook=_pairs_to_dict)
    except json.JSONDecodeError as e:
        raise CodecError(f"line {lineno}: invalid JSON: {e.msg} at column {e.colno}") from None
    except ValueError as e:
        raise CodecError(f"line {lineno}: {e}") from None
    try:
        return _normalize(obj)
    except (TypeError, ValueError) as e:
        raise CodecError(f"line {lineno}: {e}") from None


def _to_text(data: bytes) -> str:
    if not isinstance(data, (bytes, bytearray, memoryview)):
        raise TypeError(f"expected bytes, got {type(data).__name__}")
    try:
        return bytes(data).decode("utf-8")
    except UnicodeDecodeError as e:
        raise CodecError(f"input is not valid UTF-8 ({e.reason} at byte {e.start})") from None


def _iter_records(data: bytes) -> Iterator[dict]:
    """Yield the records in ``data`` one at a time, validating as it goes."""
    text = _to_text(data)
    if text.startswith(_BOM):
        text = text[1:]
    if text and not text.endswith("\n"):
        raise CodecError("truncated input: last line is not newline-terminated")
    for lineno, line in enumerate(text.split("\n"), 1):
        rec = _parse_line(line, lineno)
        if rec is not None:
            yield rec


# --------------------------------------------------------------------------
# Public interface
# --------------------------------------------------------------------------


def encode(records: list[dict]) -> bytes:
    """Serialize ``records`` to UTF-8 JSON lines, one record per line."""
    return "".join(_format_line(r) for r in _normalize_all(records)).encode("utf-8")


def decode(data: bytes) -> list[dict]:
    """Parse bytes produced by ``encode``; raise ``CodecError`` if malformed."""
    return list(_iter_records(data))


def record_count(data: bytes) -> int:
    """Return the number of records in ``data``.

    Validates every line exactly as ``decode`` does (so malformed input
    raises ``CodecError``) but never holds more than one record in memory.
    """
    return sum(1 for _ in _iter_records(data))


def dump_text(data: bytes) -> str:
    """Render an encoding as human-readable text, one line per record.

    The wire format already is that text, so this validates ``data`` and
    returns it in canonical form: hand-edited files come back with blank
    lines dropped, CRLF and BOM removed, and keys in the standard order.
    Returns ``""`` for the empty encoding.
    """
    return "".join(_format_line(r) for r in _iter_records(data))


def filter_sensor(data: bytes, sensor_id: int) -> bytes:
    """Return a valid encoding of only ``sensor_id``'s records, in order."""
    if isinstance(sensor_id, bool) or not isinstance(sensor_id, int):
        raise TypeError(f"sensor_id must be an integer, got {type(sensor_id).__name__}")
    lo, hi = _INT_RANGES["sensor_id"]
    if not lo <= sensor_id <= hi:
        raise ValueError(f"sensor_id={sensor_id} out of range {lo}..{hi}")
    return "".join(
        _format_line(r) for r in _iter_records(data) if r["sensor_id"] == sensor_id
    ).encode("utf-8")


def merge(a: bytes, b: bytes) -> bytes:
    """Merge two encodings into one, sorted by ``ts``.

    Both inputs are validated exactly as ``decode`` validates them, so a
    malformed input raises ``CodecError``. Neither input has to be sorted
    already. The sort is stable: records with equal ``ts`` keep their
    relative order, with every record from ``a`` placed before every record
    from ``b``. Merging with the empty encoding returns the other input's
    records in ``ts`` order.
    """
    rows = list(_iter_records(a))
    rows.extend(_iter_records(b))
    rows.sort(key=lambda r: r["ts"])  # list.sort is stable
    return "".join(_format_line(r) for r in rows).encode("utf-8")


def encode_stream(records: Iterable[dict], fp: BinaryIO) -> None:
    """Write ``records`` to binary file object ``fp`` in ``encode``'s format.

    All records are validated before anything is written, so a validation
    error leaves ``fp`` untouched. Lines are written in chunks rather than
    as one string.
    """
    rows = _normalize_all(records)
    for start in range(0, len(rows), _CHUNK_RECORDS):
        chunk = "".join(_format_line(r) for r in rows[start : start + _CHUNK_RECORDS])
        fp.write(chunk.encode("utf-8"))


def decode_stream(fp: BinaryIO) -> list[dict]:
    """Read an encoding from binary file object ``fp`` and return its records.

    Reads ``fp`` to EOF one line at a time, so the whole file never has to
    sit in memory. Accepts exactly what ``decode`` accepts and raises
    ``CodecError`` on the same inputs.
    """
    out: list[dict] = []
    for lineno, raw in enumerate(fp, 1):
        if not raw.endswith(b"\n"):
            raise CodecError("truncated input: last line is not newline-terminated")
        try:
            line = raw.decode("utf-8")
        except UnicodeDecodeError as e:
            raise CodecError(
                f"line {lineno}: not valid UTF-8 ({e.reason} at byte {e.start})"
            ) from None
        if lineno == 1 and line.startswith(_BOM):
            line = line[1:]
        rec = _parse_line(line, lineno)
        if rec is not None:
            out.append(rec)
    return out
