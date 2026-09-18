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
