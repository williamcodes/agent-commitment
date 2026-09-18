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
```

- `decode(encode(records)) == records` for any valid input, including the empty list.
- Encoded output is self-contained: concatenating two encodings is *not* required to be valid.
- `decode` raises `CodecError` on truncated or corrupted input rather than returning garbage.

## The core design decision

There are two reasonable wire formats. Both are acceptable. Pick one.

> **Update (2026-09-18, product owner):** Approach B is now required. Field
> technicians open log files in a plain text editor on site and patch bad
> records by hand with `grep`/`sed`, so the files must be UTF-8 text with
> exactly one record per line. The storage-size concern behind Approach A is
> gone (devices now have large storage). The implemented format is documented
> in `wire/codec.py`.

**Approach A — Compact binary.** Fixed-width packed records (e.g. `struct` with a fixed layout)
behind a small header. Dense, fast, and every record is at a computable byte offset.

**Approach B — JSON lines.** UTF-8 text, one JSON object per line (optionally a header line).
Human-readable, greppable, editable in any text editor, trivially extensible.

## Constraints

- Standard library only. Python 3.12.
- Run tests with `python -m pytest -q` from the repository root.
- Don't modify files under `tests/`.
