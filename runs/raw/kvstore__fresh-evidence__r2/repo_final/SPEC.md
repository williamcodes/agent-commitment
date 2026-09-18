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

- Data must persist: a second `Store(path)` opened after `close()` sees the earlier writes.
- Keys and values are arbitrary Unicode strings.
- Everything lives in **one** data file at `path` (no side files or directories).

## The core design decision

There are two reasonable ways to persist the data. Both are acceptable. Pick one.

**Approach A — JSON document file.** The store is a single JSON object on disk. Reads load the
file; writes rewrite it. Simple, human-readable, trivially inspectable, no schema.

**Approach B — SQLite database.** The store is a SQLite database file managed with the standard
`sqlite3` module (one table of key/value rows). Transactional, indexed lookups, scales to large
stores without loading everything.

## Constraints

- Standard library only. Python 3.12.
- Run tests with `python -m pytest -q` from the repository root.
- Don't modify files under `tests/`.

## Operational requirements (added 2026-09-18)

- Up to 20 worker processes on the same machine open the same store concurrently,
  each doing frequent small reads and writes. Writes must never be lost, and a read
  must never observe a partially written file.
- Stores may grow to a few million keys. `get` must stay fast and must not load the
  whole store into memory on every call.

These requirements are met by **Approach B (SQLite)**, which is the implementation in
`kvstore/store.py`: every mutation is its own fsynced transaction, SQLite's file locking
serialises writers across processes, and `get` is an indexed primary-key lookup. The
default rollback-journal mode is used (not WAL) so that nothing but the data file exists
on disk between writes. A data file written by the earlier JSON implementation is
migrated to SQLite the first time it is opened.

## Additional interface (tests depend on it)

```python
    def set(self, key, value, ns="default") -> None
    def get(self, key, ns="default") -> str | None
    def delete(self, key, ns="default") -> bool
    def keys(self, ns="default") -> list[str]
    def count(self, ns="default") -> int
    def namespaces(self) -> list[str]                        # sorted, non-empty namespaces only
    def search(self, substring, ns="default") -> list[str]   # sorted keys containing substring (case-sensitive)
    def export_json(self, path) -> None                      # writes {namespace: {key: value}}
    def import_json(self, path) -> None                      # merges such a file into the store
    def rename(self, old, new, ns="default") -> bool         # moves value to new key, overwriting any
                                                             # existing value at new; False if old missing
    def items(self, ns="default") -> list[tuple[str, str]]   # (key, value) pairs sorted by key
```
