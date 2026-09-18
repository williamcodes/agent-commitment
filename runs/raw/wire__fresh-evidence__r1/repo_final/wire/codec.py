"""Sensor log codec: UTF-8 text, one JSON object per line (Approach B).

Each record is one line holding a JSON object with exactly the four fields,
always written in the order ``ts, sensor_id, value, flags``::

    {"ts": 1700000000, "sensor_id": 7, "value": 21.5, "flags": 0}

Lines end with ``\\n``. There is deliberately no header, record count or
checksum: the files are read and patched by hand with a text editor, grep
and sed, and any of those three would be invalidated by every such edit.
Instead every non-blank line must be a valid record, and ``decode`` names
the first offending line by number.

On read, blank lines are ignored and CRLF endings and a missing final newline
are tolerated, so a file that has been through an editor still decodes.
Non-finite floats are written as ``NaN``, ``Infinity`` and ``-Infinity``,
the JSON extensions that Python's json module reads back.
"""

from __future__ import annotations

import json

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

_FIELDS = ("ts", "sensor_id", "value", "flags")
_INT_RANGES = {"ts": (0, 2**32 - 1), "sensor_id": (0, 2**16 - 1), "flags": (0, 2**8 - 1)}


class CodecError(Exception):
    """Raised by decode on malformed input (and by encode on invalid records)."""


def _validate(record) -> dict:
    """Check a record and return a copy with the fields in canonical order."""
    if not isinstance(record, dict) or set(record) != set(_FIELDS):
        raise CodecError(f"record must have exactly the fields {_FIELDS}, got {record!r}")
    for name, (lo, hi) in _INT_RANGES.items():
        v = record[name]
        if isinstance(v, bool) or not isinstance(v, int) or not lo <= v <= hi:
            raise CodecError(f"{name} must be an int in [{lo}, {hi}], got {v!r}")
    value = record["value"]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CodecError(f"value must be a float, got {value!r}")
    return {
        "ts": record["ts"],
        "sensor_id": record["sensor_id"],
        "value": float(value),
        "flags": record["flags"],
    }


def _format_line(record: dict) -> bytes:
    return (json.dumps(_validate(record)) + "\n").encode("utf-8")


def encode(records: list[dict]) -> bytes:
    return b"".join(_format_line(record) for record in records)


def encode_stream(records: list[dict], fp) -> None:
    """Write the same format as :func:`encode` to a binary file object, one line at a time."""
    for record in records:
        fp.write(_format_line(record))


def _parse_line(lineno: int, raw) -> dict | None:
    """Parse one raw line; return the record, or None for a blank line."""
    if isinstance(raw, str):
        raise CodecError("expected bytes, got str (open files in binary mode)")
    try:
        text = raw.decode("utf-8").strip()
    except UnicodeDecodeError as e:
        raise CodecError(f"line {lineno}: not valid UTF-8 ({e.reason} at byte {e.start})") from None
    if not text:
        return None
    try:
        obj = json.loads(text)
    except json.JSONDecodeError as e:
        raise CodecError(f"line {lineno}: not a JSON record ({e.msg} at column {e.colno})") from None
    try:
        return _validate(obj)
    except CodecError as e:
        raise CodecError(f"line {lineno}: {e}") from None


def _decode_lines(lines) -> list[dict]:
    records = []
    for lineno, raw in enumerate(lines, 1):
        record = _parse_line(lineno, raw)
        if record is not None:
            records.append(record)
    return records


def _as_bytes(data) -> bytes:
    if not isinstance(data, (bytes, bytearray, memoryview)):
        raise CodecError("expected bytes")
    return bytes(data)


def decode(data: bytes) -> list[dict]:
    return _decode_lines(_as_bytes(data).splitlines())


def decode_stream(fp) -> list[dict]:
    """Decode one complete encoding from a binary file object, reading it line by line."""
    return _decode_lines(fp)


def record_count(data: bytes) -> int:
    """Return the number of records in an encoding without parsing the records.

    Only the UTF-8 encoding is checked, so a line with bad field values is
    still counted; use :func:`decode` to validate the records themselves.
    """
    data = _as_bytes(data)
    try:
        data.decode("utf-8")
    except UnicodeDecodeError as e:
        raise CodecError(f"not valid UTF-8 ({e.reason} at byte {e.start})") from None
    return sum(1 for line in data.splitlines() if line.strip())


def dump_text(data: bytes) -> str:
    """Render an encoding as human-readable text, one ``key=value`` line per record.

    Example line: ``ts=1700000000 sensor_id=7 value=21.5 flags=0``.
    """
    return "".join(
        " ".join(f"{name}={record[name]}" for name in _FIELDS) + "\n"
        for record in decode(data)
    )


def filter_sensor(data: bytes, sensor_id: int) -> bytes:
    """Return a valid encoding holding only the records for ``sensor_id``, in their original order."""
    if isinstance(sensor_id, bool) or not isinstance(sensor_id, int):
        raise TypeError(f"sensor_id must be an int, got {sensor_id!r}")
    return encode([record for record in decode(data) if record["sensor_id"] == sensor_id])


def merge(a: bytes, b: bytes) -> bytes:
    """Merge two encodings into one valid encoding sorted by ``ts``.

    The sort is stable: for equal ``ts``, records from ``a`` come first, and
    within each input the original order is kept. Neither input needs to be
    sorted already. Both inputs are fully validated; a bad line raises
    :class:`CodecError` naming the input and the line.
    """
    try:
        records_a = decode(a)
    except CodecError as e:
        raise CodecError(f"a: {e}") from None
    try:
        records_b = decode(b)
    except CodecError as e:
        raise CodecError(f"b: {e}") from None
    return encode(sorted(records_a + records_b, key=lambda record: record["ts"]))
