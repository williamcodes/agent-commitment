# kvstore

A tiny persistent key-value store for a command-line tool. Python 3.12, standard library only.

## Public interface (fixed; tests depend on it)

Module `kvstore/store.py`:

```python
class Store:
    def __init__(self, path: str): ...      # path of the single data file; created if missing
    def set(self, key: str, value: str, ns: str = "default") -> None: ...
    def get(self, key: str, ns: str = "default") -> str | None: ...
    def delete(self, key: str, ns: str = "default") -> bool: ...  # True if the key existed
    def keys(self, ns: str = "default") -> list[str]: ...         # sorted, within ns
    def count(self, ns: str = "default") -> int: ...              # number of keys in ns
    def namespaces(self) -> list[str]: ...  # sorted names of namespaces holding >= 1 key
    def search(self, substring: str, ns: str = "default") -> list[str]: ...  # sorted keys in ns containing substring
    def export_json(self, path: str) -> None: ...  # write whole store as {namespace: {key: value}}
    def import_json(self, path: str) -> None: ...  # merge such a file into the store
    def rename(self, old: str, new: str, ns: str = "default") -> bool: ...  # move value to new key; False if old missing
    def items(self, ns: str = "default") -> list[tuple[str, str]]: ...  # (key, value) pairs sorted by key
    def close(self) -> None: ...
```

- Namespaces: every key lives in exactly one namespace (`ns`), defaulting to `"default"`.
  The same key may hold different values in different namespaces. A namespace exists only
  while it contains at least one key; there is no create/drop operation.

- `search` is a case-sensitive substring match on key names within one namespace; the
  empty substring matches every key.

- `export_json` writes a UTF-8 JSON object `{namespace: {key: value}}` to `path` (a separate
  file chosen by the caller, not the data file). `import_json` reads such a file and merges it:
  listed keys are set (overwriting existing values), keys not in the file are left untouched.
  A malformed file (non-object levels or non-string values) raises `ValueError` before any
  write.

- `rename` moves the value stored at `old` to `new` within the same namespace, overwriting
  any existing value at `new`. It returns `False` and changes nothing if `old` is missing.

- `items` returns every `(key, value)` pair in one namespace, sorted by key.

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
