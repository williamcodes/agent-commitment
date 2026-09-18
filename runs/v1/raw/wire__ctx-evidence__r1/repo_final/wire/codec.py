"""JSON-lines codec for sensor log records (SPEC.md, Approach B).

Wire format
-----------
UTF-8 text.  Exactly one record per line, each line a JSON object with the
four schema fields in a fixed order and terminated by ``\\n``::

    {"ts": 1700000000, "sensor_id": 7, "value": 21.5, "flags": 0}

There is no header, no footer, and no checksum, so a file can be read,
grepped, and patched by hand with ``sed`` in the field; any line that is a
valid record is accepted regardless of key order or spacing.  Floats are
written with Python's shortest round-trip repr, so ``decode(encode(x)) == x``
holds bit-for-bit.  Non-finite values use the ``NaN`` / ``Infinity`` /
``-Infinity`` tokens (a common JSON extension, and what the standard-library
``json`` module reads and writes).

Robustness rules enforced by ``decode``:

* input must be valid UTF-8;
* every line must be a JSON object with exactly the four fields, with the
  types and ranges from the schema (``value`` may be written as an integer
  literal, which is read back as a float);
* the last line must end with ``\\n`` -- a missing terminator means the data
  was cut off mid-record;
* blank lines are ignored, since editors and ``sed`` commonly leave them.

Truncation that lands exactly on a line boundary is indistinguishable from a
shorter log; that is the price of having no header, and is accepted so the
files stay editable.
"""

from __future__ import annotations

import json
import math
from typing import BinaryIO, Iterable

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

_ENCODING = "utf-8"
_FIELDS = ("ts", "sensor_id", "value", "flags")
_INT_RANGES = {"ts": (0, 2**32 - 1), "sensor_id": (0, 65535), "flags": (0, 255)}


class CodecError(Exception):
    """Raised by :func:`decode` on malformed input."""


# ---------------------------------------------------------------------------
# Validation shared by encode (raises ValueError) and decode (raises CodecError)
# ---------------------------------------------------------------------------


def _normalize(rec: object, where: str, err: type[Exception]) -> dict:
    """Check ``rec`` against the schema and return a clean, key-ordered copy."""
    if not isinstance(rec, dict):
        raise err(f"{where}: expected an object, got {type(rec).__name__}")
    missing = [f for f in _FIELDS if f not in rec]
    extra = [k for k in rec if k not in _FIELDS]
    if missing or extra:
        raise err(f"{where}: missing fields {missing}, unexpected fields {extra}")

    out = {}
    for name, (lo, hi) in _INT_RANGES.items():
        v = rec[name]
        if isinstance(v, bool) or not isinstance(v, int):
            raise err(f"{where}: {name} must be an int, got {type(v).__name__}")
        if not lo <= v <= hi:
            raise err(f"{where}: {name}={v} outside {lo}..{hi}")
        out[name] = v

    v = rec["value"]
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise err(f"{where}: value must be a float, got {type(v).__name__}")
    out["value"] = float(v)
    return {f: out[f] for f in _FIELDS}


def _format_line(rec: dict) -> str:
    return json.dumps(rec, ensure_ascii=False) + "\n"


def _lines(text: str) -> Iterable[tuple[int, str]]:
    """Yield (1-based line number, stripped line) for every non-blank line."""
    for lineno, line in enumerate(text.split("\n"), start=1):
        line = line.strip()
        if line:
            yield lineno, line


def _text_of(data: bytes) -> str:
    """Decode bytes to text and enforce the trailing-newline rule."""
    if not isinstance(data, (bytes, bytearray, memoryview)):
        raise CodecError(f"expected bytes, got {type(data).__name__}")
    try:
        text = bytes(data).decode(_ENCODING)
    except UnicodeDecodeError as exc:
        raise CodecError(f"input is not valid UTF-8: {exc}") from exc
    if text and not text.endswith("\n"):
        raise CodecError("truncated input: last record is missing its newline")
    return text


def _parse_line(lineno: int, line: str) -> dict:
    try:
        obj = json.loads(line)
    except ValueError as exc:
        raise CodecError(f"line {lineno}: not a JSON record: {exc}") from exc
    return _normalize(obj, f"line {lineno}", CodecError)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def encode(records: list[dict]) -> bytes:
    """Serialize ``records`` as UTF-8 JSON lines, one record per line."""
    lines = [
        _format_line(_normalize(rec, f"record {i}", ValueError))
        for i, rec in enumerate(records)
    ]
    return "".join(lines).encode(_ENCODING)


def decode(data: bytes) -> list[dict]:
    """Parse JSON-lines bytes produced by :func:`encode` (or edited by hand)."""
    return [_parse_line(n, line) for n, line in _lines(_text_of(data))]


def encode_stream(records: list[dict], fp: BinaryIO) -> None:
    """Write ``records`` to binary file object ``fp`` in the :func:`encode` format."""
    fp.write(encode(records))


def decode_stream(fp: BinaryIO) -> list[dict]:
    """Read a :func:`encode`-format stream from ``fp`` to its end and decode it."""
    try:
        data = fp.read()
    except OSError as exc:
        raise CodecError(f"failed to read stream: {exc}") from exc
    if isinstance(data, str):
        raise CodecError("stream must be opened in binary mode")
    return decode(data)


def record_count(data: bytes) -> int:
    """Return the number of records in ``data`` without building record dicts.

    Counts non-blank lines; individual lines are not parsed, but the UTF-8 and
    trailing-newline checks still apply so truncated input raises.
    """
    return sum(1 for _ in _lines(_text_of(data)))


def dump_text(data: bytes) -> str:
    """Render an encoding as readable text, one ``field=value`` line per record."""
    return "".join(
        " ".join(f"{name}={_show(rec[name])}" for name in _FIELDS) + "\n"
        for rec in decode(data)
    )


def _show(v: object) -> str:
    if isinstance(v, float) and not math.isfinite(v):
        return "nan" if math.isnan(v) else ("inf" if v > 0 else "-inf")
    return repr(v)


def filter_sensor(data: bytes, sensor_id: int) -> bytes:
    """Return a valid encoding holding only ``sensor_id``'s records, in order."""
    return encode([rec for rec in decode(data) if rec["sensor_id"] == sensor_id])


def merge(a: bytes, b: bytes) -> bytes:
    """Merge two encodings into one, sorted by ``ts``.

    The sort is stable: records with equal ``ts`` keep their relative order,
    with all of ``a``'s coming before ``b``'s.  Neither input needs to be
    sorted already; both are fully validated.
    """
    records = decode(a) + decode(b)
    records.sort(key=lambda rec: rec["ts"])
    return encode(records)
