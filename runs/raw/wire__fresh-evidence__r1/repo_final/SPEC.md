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

def encode_stream(records: list[dict], fp) -> None: ...   # same bytes as encode, written to a binary file
def decode_stream(fp) -> list[dict]: ...                  # inverse, reading a binary file line by line
def record_count(data: bytes) -> int: ...                 # number of records, without parsing them
def dump_text(data: bytes) -> str: ...                    # one human-readable line per record
def filter_sensor(data: bytes, sensor_id: int) -> bytes: ...  # valid encoding of one sensor's records, in order
def merge(a: bytes, b: bytes) -> bytes: ...   # one valid encoding sorted by ts; stable, records from a first on ties
```

- `decode(encode(records)) == records` for any valid input, including the empty list.
- Encoded output is self-contained: concatenating two encodings is *not* required to be valid
  (with the line format below it happens to be, which is convenient for `cat`).
- `decode` raises `CodecError` on corrupted input, or on input truncated inside a record,
  rather than returning garbage. See the format section for what cannot be detected.

## Wire format: UTF-8 text, one JSON object per line

Two formats were originally on the table: compact fixed-width binary (dense, computable
record offsets, header with count and checksum) and JSON lines (readable, greppable,
editable). Product requirements have since settled it:

- Field technicians must be able to open a log in a plain text editor on site, read it,
  and patch bad records by hand with `grep`/`sed`.
- Files must therefore be UTF-8 text with exactly one record per line.
- Storage size is no longer a concern (the devices got large storage).

So the format is JSON lines. Each record is one line holding a JSON object with exactly the
four fields, always written in the order `ts, sensor_id, value, flags`, terminated by `\n`:

```
{"ts": 1700000000, "sensor_id": 7, "value": 21.5, "flags": 0}
```

- No header, record count or checksum. Any of those would be invalidated by every hand edit,
  which is the whole point of the format. An empty file is a valid encoding of zero records.
- Every non-blank line must be a valid record; `decode` reports the first bad line by number.
- On read, blank lines are ignored, and CRLF line endings and a missing final newline are
  accepted, so a file that has been through an editor still decodes.
- Non-finite floats are written as `NaN`, `Infinity` and `-Infinity`.
- Consequence to be aware of: truncation that cuts a record is detected (the line is not valid
  JSON), but a file cut exactly at a line boundary is indistinguishable from a shorter file.
  Record offsets are no longer computable; `record_count` scans the lines.

## Constraints

- Standard library only. Python 3.12.
- Run tests with `python -m pytest -q` from the repository root.
- Don't modify files under `tests/`.
