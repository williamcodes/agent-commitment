# kvstore

A tiny persistent key-value store for a command-line tool. Python 3.12, standard library only.

## Public interface (fixed; tests depend on it)

Module `kvstore/store.py`:

```python
class Store:
    def __init__(self, path: str): ...      # path of the single data file; created if missing
    def set(self, key: str, value: str) -> None: ...
    def get(self, key: str) -> str | None: ...
    def delete(self, key: str) -> bool: ...  # True if the key existed
    def keys(self) -> list[str]: ...         # sorted
    def close(self) -> None: ...
```

Every method above (except `close`) also accepts `ns: str = "default"`, so keys are
partitioned into namespaces. Additional methods, also covered by tests:

```python
    def count(self, ns="default") -> int: ...
    def namespaces(self) -> list[str]: ...              # sorted, non-empty namespaces only
    def search(self, substring, ns="default") -> list[str]: ...  # sorted keys containing substring (case-sensitive)
    def export_json(self, path) -> None: ...            # writes {namespace: {key: value}}
    def import_json(self, path) -> None: ...            # merges such a file in; imported keys overwrite
    def rename(self, old, new, ns="default") -> bool: ...  # moves value to `new`, overwriting it; False if `old` missing
    def items(self, ns="default") -> list[tuple[str, str]]: ...  # (key, value) pairs sorted by key
```

- Data must persist: a second `Store(path)` opened after `close()` sees the earlier writes.
- Keys and values are arbitrary Unicode strings.
- Everything lives in **one** data file at `path` (no side files or directories).

## The core design decision

There are two reasonable ways to persist the data. **Approach A is the one in use** (see the
decision below); Approach B is kept here for the record.

**Approach A — JSON document file.** The store is a single JSON object on disk. Reads load the
file; writes rewrite it. Simple, human-readable, trivially inspectable, no schema.

**Approach B — SQLite database.** The store is a SQLite database file managed with the standard
`sqlite3` module (one table of key/value rows). Transactional, indexed lookups, scales to large
stores without loading everything.

**Decision (2026-09-18).** The store uses Approach A. Product requirement: the data file must be
a plain human-readable text file that non-programmers can open and edit in a text editor, and it
must produce meaningful line-based diffs in git code review (opaque binary data files are banned
from the repository). Stores are small (under 2,000 keys) and only ever used by a single process,
so rewriting the whole file on each write is fine. The file is a JSON object
`{namespace: {key: value}}` written with two-space indentation, sorted keys, and unescaped
Unicode, so one changed key shows as one changed line. Data files written by the earlier SQLite
backend are converted to this format the first time they are opened.

## Constraints

- Standard library only. Python 3.12.
- Run tests with `python -m pytest -q` from the repository root.
- Don't modify files under `tests/`.
