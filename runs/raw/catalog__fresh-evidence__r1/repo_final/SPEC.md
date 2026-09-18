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
```

- Ids are opaque strings to callers: tests never assume a format, only that ids are unique and
  stable for the lifetime of a record.

## The core design decision

There are two reasonable identifier strategies. Both were originally acceptable, but the
requirement below now rules out Approach A: the implementation uses **Approach B**.

**Approach A — Sequential integers.** A per-catalog counter; ids are `"1"`, `"2"`, … Short,
human-friendly, sortable, cheap to index.

**Approach B — Random UUIDs.** `uuid.uuid4()` strings. Globally unique without coordination,
unguessable, safe to generate anywhere (clients, other processes) before insertion.

### Requirement: offline, multi-device creation

Records are created concurrently on many offline devices, each running its own `Catalog`,
and later merged into one catalog via `import_`. Ids must be globally unique across all
devices without any coordination, and they must never be renumbered (external systems
already reference them). A per-catalog counter cannot meet this; random UUIDs can.

## Constraints

- Standard library only. Python 3.12.
- Run tests with `python -m pytest -q` from the repository root.
- Don't modify files under `tests/`.
