"""In-memory catalog of book records.

Identifier strategy: Approach A (sequential integers). A per-catalog counter
issues ids "1", "2", ... The counter only ever increases, so an id is never
reused after its record is deleted, which keeps ids stable and unique for the
lifetime of the catalog.
"""

from __future__ import annotations

import json

_MUTABLE_FIELDS = frozenset({"title", "author"})


class NotFound(Exception):
    """Raised when a record id does not exist in the catalog."""


class Catalog:
    def __init__(self) -> None:
        # dict preserves insertion order, which gives us creation order for list().
        self._records: dict[str, dict] = {}
        # Tags are kept beside the records so get()/list() keep returning
        # exactly {"id", "title", "author"}.
        self._tags: dict[str, set[str]] = {}
        self._next_id = 1

    def _new_id(self) -> str:
        record_id = str(self._next_id)
        self._next_id += 1
        return record_id

    def _lookup(self, record_id: str) -> dict:
        try:
            return self._records[record_id]
        except KeyError:
            raise NotFound(record_id) from None

    def create(self, title: str, author: str) -> str:
        record_id = self._new_id()
        self._records[record_id] = {"id": record_id, "title": title, "author": author}
        self._tags[record_id] = set()
        return record_id

    def bulk_create(self, items: list[tuple[str, str]]) -> list[str]:
        """Create one record per (title, author) pair; returns the new ids in order."""
        return [self.create(title, author) for title, author in items]

    def clone(self, record_id: str) -> str:
        """Create a new record with the same title and author; returns the new id."""
        source = self._lookup(record_id)
        return self.create(source["title"], source["author"])

    def count(self) -> int:
        return len(self._records)

    def get(self, record_id: str) -> dict:
        return dict(self._lookup(record_id))

    def update(self, record_id: str, **fields) -> dict:
        unknown = set(fields) - _MUTABLE_FIELDS
        if unknown:
            raise ValueError(f"cannot update field(s): {', '.join(sorted(unknown))}")
        record = self._lookup(record_id)
        record.update(fields)
        return dict(record)

    def delete(self, record_id: str) -> None:
        self._lookup(record_id)
        del self._records[record_id]
        del self._tags[record_id]

    def list(self) -> list[dict]:
        return [dict(r) for r in self._records.values()]

    def tag(self, record_id: str, tag: str) -> None:
        self._lookup(record_id)
        self._tags[record_id].add(tag)

    def untag(self, record_id: str, tag: str) -> None:
        self._lookup(record_id)
        self._tags[record_id].discard(tag)

    def tags(self, record_id: str) -> list[str]:
        self._lookup(record_id)
        return sorted(self._tags[record_id])

    def by_tag(self, tag: str) -> list[dict]:
        """Records carrying ``tag``, in creation order."""
        return [dict(r) for rid, r in self._records.items() if tag in self._tags[rid]]

    def find(self, substring: str) -> list[dict]:
        """Records whose title contains ``substring`` (case-insensitive), in creation order."""
        needle = substring.casefold()
        return [dict(r) for r in self._records.values() if needle in r["title"].casefold()]

    def export(self) -> str:
        """JSON array of records in creation order; each carries a sorted ``tags`` list."""
        return json.dumps([{**r, "tags": sorted(self._tags[rid])} for rid, r in self._records.items()])

    def import_(self, dump: str) -> None:
        """Load records from an ``export()`` dump, keeping their ids.

        Works on an empty or populated catalog. The dump is validated fully
        before anything is inserted, so a bad dump leaves the catalog unchanged.
        Raises ValueError on malformed input or on an id that already exists.
        """
        try:
            data = json.loads(dump)
        except json.JSONDecodeError as e:
            raise ValueError(f"invalid catalog dump: {e}") from None
        if not isinstance(data, list):
            raise ValueError("catalog dump must be a JSON array")

        incoming: dict[str, dict] = {}
        incoming_tags: dict[str, set[str]] = {}
        for item in data:
            if not isinstance(item, dict) or not {"id", "title", "author"} <= set(item) <= {"id", "title", "author", "tags"}:
                raise ValueError(f"malformed record in dump: {item!r}")
            record_id = item["id"]
            if not isinstance(record_id, str) or not record_id:
                raise ValueError(f"record id must be a non-empty string: {record_id!r}")
            if record_id in self._records or record_id in incoming:
                raise ValueError(f"duplicate record id: {record_id}")
            tags = item.get("tags", [])
            if not isinstance(tags, list) or not all(isinstance(t, str) for t in tags):
                raise ValueError(f"tags must be a list of strings: {tags!r}")
            incoming[record_id] = {"id": record_id, "title": item["title"], "author": item["author"]}
            incoming_tags[record_id] = set(tags)

        self._records.update(incoming)
        self._tags.update(incoming_tags)
        # Keep the sequential counter ahead of any imported numeric id so that
        # future create() calls never reuse an imported id.
        for record_id in incoming:
            if record_id.isdigit():
                self._next_id = max(self._next_id, int(record_id) + 1)
