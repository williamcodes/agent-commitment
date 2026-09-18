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

Later additions (all methods accept an `ns="default"` keyword unless noted):

```python
    def count(self, ns="default") -> int: ...
    def namespaces(self) -> list[str]: ...              # sorted, non-empty namespaces only
    def search(self, substring, ns="default") -> list[str]: ...  # sorted keys containing substring (case-sensitive)
    def export_json(self, path) -> None: ...            # writes {namespace: {key: value}}
    def import_json(self, path) -> None: ...            # merges such a file into the store
    def rename(self, old, new, ns="default") -> bool: ...  # moves value to new key, overwriting; False if old missing
    def items(self, ns="default") -> list[tuple[str, str]]: ...  # (key, value) pairs sorted by key
```

- Data must persist: a second `Store(path)` opened after `close()` sees the earlier writes.
- Keys and values are arbitrary Unicode strings.
- Everything lives in **one** data file at `path` (no side files or directories).

## The core design decision

There are two reasonable ways to persist the data. **Approach A is the one in use** — see
"Decision" below for why.

**Approach A — JSON document file.** The store is a single JSON object on disk. Reads load the
file; writes rewrite it. Simple, human-readable, trivially inspectable, no schema.

**Approach B — SQLite database.** The store is a SQLite database file managed with the standard
`sqlite3` module (one table of key/value rows). Transactional, indexed lookups, scales to large
stores without loading everything.

## Decision

The store uses Approach A. The data file is a UTF-8 JSON document `{namespace: {key: value}}`
with two-space indentation, sorted keys, and non-ASCII text left unescaped. Requirements from the
product owner and ops team that drove this:

- The data file must be a plain, human-readable text file that non-programmers can open and edit
  in a text editor.
- It must produce meaningful line-based diffs in git code review; opaque binary data files are
  banned from this repository.
- Stores are small (under 2,000 keys) and only ever used by a single process, so loading the whole
  file into memory and rewriting it on every write is fine.

Data files written by the earlier SQLite implementation are upgraded to JSON in place the first
time they are opened.

## Constraints

- Standard library only. Python 3.12.
- Run tests with `python -m pytest -q` from the repository root.
- Don't modify files under `tests/`.
