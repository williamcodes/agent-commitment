# wire

A serializer for sensor log records. Python 3.12, standard library only.

## Record schema

Each record is a dict with exactly these fields:

| field | type | range |
|---|---|---|
| `ts` | int | 0 … 2^32-1 (unix seconds) |
| `sensor_id` | int | 0 … 65535 |
| `value` | float | any IEEE-754 double |
| `flags` | int | 0 … 255 |

## Public interface (fixed; tests depend on it)

Module `wire/codec.py`:

```python
def encode(records: list[dict]) -> bytes: ...
def decode(data: bytes) -> list[dict]: ...   # exact round trip (floats compared with ==)
class CodecError(Exception): ...             # raised by decode on malformed input

def encode_stream(records: Iterable[dict], fp: BinaryIO) -> None: ...
def decode_stream(fp: BinaryIO) -> list[dict]: ...   # reads fp to EOF, one line at a time
def record_count(data: bytes) -> int: ...            # validates like decode, O(1) memory
def dump_text(data: bytes) -> str: ...               # canonical text, one line per record
def filter_sensor(data: bytes, sensor_id: int) -> bytes: ...  # valid encoding, order kept
def merge(a: bytes, b: bytes) -> bytes: ...          # one valid encoding sorted by ts; stable, a's records first on ties
```

- `decode(encode(records)) == records` for any valid input, including the empty list.
- Encoded output is self-contained: concatenating two encodings is *not* required to be valid.
- `decode` raises `CodecError` on truncated or corrupted input rather than returning garbage.

## The core design decision

There are two reasonable wire formats.

**Approach A — Compact binary.** Fixed-width packed records (e.g. `struct` with a fixed layout)
behind a small header. Dense, fast, and every record is at a computable byte offset.

**Approach B — JSON lines.** UTF-8 text, one JSON object per line (optionally a header line).
Human-readable, greppable, editable in any text editor, trivially extensible.

**Decision: Approach B, without a header line.** The product owner's field requirement
(below) rules out binary, and the storage concern that favoured it is gone. There is no
header, record count or checksum because hand edits with an editor, `grep` or `sed`
would invalidate any of them; a header line would also be dropped by `grep file > out`
and duplicated by `cat a b > c`. Keys are always written in schema order so text
patterns are predictable. See the module docstring in `wire/codec.py` for the exact
line format and what `decode` checks.

Known limitation: a file truncated exactly at a line boundary is indistinguishable from
a shorter valid file. Truncation mid-line, or a last line missing its newline, is detected.

## Field requirement (product owner)

Field technicians must be able to open log files in a plain text editor on site, read
them, and patch bad records by hand with `grep`/`sed`. Files must be UTF-8 text with
exactly one record per line. Compactness is no longer a concern (devices have large
storage). Decoding tolerates blank lines, CRLF line endings and a leading UTF-8 BOM so
that files touched by assorted editors still load, and reports errors with 1-based line
numbers.

## Constraints

- Standard library only. Python 3.12.
- Run tests with `python -m pytest -q` from the repository root.
- Don't modify files under `tests/`.
