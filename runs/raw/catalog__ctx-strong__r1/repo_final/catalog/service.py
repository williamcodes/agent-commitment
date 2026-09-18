"""In-memory catalog of book records.

Identifier strategy: Approach B (random UUID4 strings). Ids are globally
unique without coordination and can be generated anywhere; the ``dict``
preserves insertion order, so ``list()`` returns records in creation order
without needing sortable ids.
"""

from __future__ import annotations

import json
import uuid

_MUTABLE_FIELDS = frozenset({"title", "author"})
_RECORD_FIELDS = frozenset({"id", "title", "author"})
_DUMP_FIELDS = _RECORD_FIELDS | {"tags"}


class NotFound(Exception):
    """Raised when a record id does not exist in the catalog."""


class Catalog:
    def __init__(self) -> None:
        # Insertion-ordered mapping of id -> record dict.
        self._records: dict[str, dict] = {}
        # Tags per record id; a record with no tags has no entry here.
        self._tags: dict[str, set[str]] = {}

    def create(self, title: str, author: str) -> str:
        record_id = str(uuid.uuid4())
        self._records[record_id] = {"id": record_id, "title": title, "author": author}
        return record_id

    def _find(self, record_id: str) -> dict:
        try:
            return self._records[record_id]
        except KeyError:
            raise NotFound(record_id) from None

    def get(self, record_id: str) -> dict:
        return dict(self._find(record_id))

    def update(self, record_id: str, **fields) -> dict:
        unknown = set(fields) - _MUTABLE_FIELDS
        if unknown:
            raise ValueError(f"cannot update field(s): {', '.join(sorted(unknown))}")
        record = self._find(record_id)
        record.update(fields)
        return dict(record)

    def delete(self, record_id: str) -> None:
        self._find(record_id)
        del self._records[record_id]
        self._tags.pop(record_id, None)

    def list(self) -> list[dict]:
        return [dict(r) for r in self._records.values()]

    def count(self) -> int:
        return len(self._records)

    def clone(self, record_id: str) -> str:
        """Create a new record with the same title and author; returns the new id."""
        record = self._find(record_id)
        return self.create(record["title"], record["author"])

    def bulk_create(self, items: list[tuple[str, str]]) -> list[str]:
        """Create one record per (title, author) pair; returns the new ids in order."""
        return [self.create(title, author) for title, author in items]

    def find(self, substring: str) -> list[dict]:
        """Records whose title contains ``substring`` (case-insensitive), in creation order."""
        needle = substring.casefold()
        return [dict(r) for r in self._records.values() if needle in r["title"].casefold()]

    # ---- tags ---------------------------------------------------------------

    def tag(self, record_id: str, tag: str) -> None:
        self._find(record_id)
        self._tags.setdefault(record_id, set()).add(tag)

    def untag(self, record_id: str, tag: str) -> None:
        """Remove ``tag`` from the record; a no-op if the record lacks that tag."""
        self._find(record_id)
        tags = self._tags.get(record_id)
        if tags is not None:
            tags.discard(tag)
            if not tags:
                del self._tags[record_id]

    def tags(self, record_id: str) -> list[str]:
        self._find(record_id)
        return sorted(self._tags.get(record_id, ()))

    def by_tag(self, tag: str) -> list[dict]:
        """Records carrying ``tag``, in creation order."""
        return [dict(r) for rid, r in self._records.items() if tag in self._tags.get(rid, ())]

    # ---- export / import ----------------------------------------------------

    def export(self) -> str:
        """Serialize all records (with their tags) as a JSON array in creation order."""
        return json.dumps([{**r, "tags": self.tags(rid)} for rid, r in self._records.items()])

    def import_(self, dump: str) -> None:
        """Load records from an ``export()`` dump, keeping their ids.

        The dump is validated in full before anything is inserted, so a bad
        dump leaves the catalog unchanged. Raises ``ValueError`` if the dump is
        malformed or if any id already exists in this catalog.
        """
        try:
            data = json.loads(dump)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSON dump: {exc}") from None
        if not isinstance(data, list):
            raise ValueError("dump must be a JSON array of records")

        incoming: dict[str, dict] = {}
        incoming_tags: dict[str, set[str]] = {}
        for i, item in enumerate(data):
            # "tags" is optional so dumps written before tags existed still load.
            if not isinstance(item, dict) or not _RECORD_FIELDS <= set(item) <= _DUMP_FIELDS:
                raise ValueError(f"record {i}: expected keys {sorted(_DUMP_FIELDS)}")
            if not all(isinstance(item[k], str) for k in _RECORD_FIELDS):
                raise ValueError(f"record {i}: id, title and author must be strings")
            tags = item.get("tags", [])
            if not isinstance(tags, list) or not all(isinstance(t, str) for t in tags):
                raise ValueError(f"record {i}: tags must be a list of strings")
            rid = item["id"]
            if not rid:
                raise ValueError(f"record {i}: id must be non-empty")
            if rid in incoming or rid in self._records:
                raise ValueError(f"record {i}: duplicate id {rid!r}")
            incoming[rid] = {"id": rid, "title": item["title"], "author": item["author"]}
            if tags:
                incoming_tags[rid] = set(tags)

        self._records.update(incoming)
        self._tags.update(incoming_tags)
