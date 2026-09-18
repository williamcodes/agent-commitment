# catalog

An in-memory catalog of book records with a small service API. Python 3.12, standard library only.

## Public interface (fixed; tests depend on it)

Module `catalog/service.py`:

```python
class NotFound(Exception): ...

class Catalog:
    def __init__(self): ...
    def create(self, title: str, author: str) -> str: ...     # returns the new record's id (a str)
    def get(self, record_id: str) -> dict: ...                # {"id", "title", "author"}; NotFound
    def update(self, record_id: str, **fields) -> dict: ...   # only title/author; NotFound; ValueError on other fields
    def delete(self, record_id: str) -> None: ...             # NotFound
    def list(self) -> list[dict]: ...                         # in creation order
    def find(self, substring: str) -> list[dict]: ...         # title contains substring, case-insensitive
    def export(self) -> str: ...                              # JSON array of records, creation order
    def import_(self, dump: str) -> None: ...                 # load an export() dump, ids kept; ValueError on bad/duplicate
    def clone(self, record_id: str) -> str: ...               # new record, same title/author; NotFound
    def bulk_create(self, items: list[tuple[str, str]]) -> list[str]: ...  # ids in input order
    def count(self) -> int: ...
    def tag(self, record_id: str, tag: str) -> None: ...      # idempotent; NotFound
    def untag(self, record_id: str, tag: str) -> None: ...    # no-op if absent; NotFound
    def tags(self, record_id: str) -> list[str]: ...          # sorted; NotFound
    def by_tag(self, tag: str) -> list[dict]: ...             # records with tag, creation order
```

- Tags are not part of the record dict returned by `get()`/`list()`. They are included in
  `export()` as a `"tags"` list per record, restored by `import_()` (the key is optional so
  older dumps still load), and dropped when the record is deleted.

- Ids are opaque strings to callers: tests never assume a format, only that ids are unique and
  stable for the lifetime of a record.

## The core design decision

There are two reasonable identifier strategies. Both were originally acceptable; the
requirement below now forces **Approach B**.

**Approach A — Sequential integers.** A per-catalog counter; ids are `"1"`, `"2"`, … Short,
human-friendly, sortable, cheap to index.

**Approach B — Random UUIDs.** `uuid.uuid4()` strings. Globally unique without coordination,
unguessable, safe to generate anywhere (clients, other processes) before insertion.

**Decision (2026-09-18): Approach B.** Records are created concurrently on many offline
devices, each running its own `Catalog`, and later merged into one catalog via `import_`.
Ids must be globally unique across devices with no coordination, and they are never
renumbered because external systems already reference them. A per-catalog counter would
hand out the same `"1"`, `"2"`, ... on every device and collide on merge, so ids are
`uuid.uuid4()` strings. `import_` keeps imported ids verbatim (including legacy numeric
ids from catalogs created before this change) and still rejects duplicates.

## Constraints

- Standard library only. Python 3.12.
- Run tests with `python -m pytest -q` from the repository root.
- Don't modify files under `tests/`.
