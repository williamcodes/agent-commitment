"""In-memory catalog of book records.

Identifier strategy: Approach A (sequential integers). Each Catalog keeps its
own counter; ids are the decimal strings "1", "2", ... Ids are never reused,
even after a delete, so they stay unique and stable for a record's lifetime.
"""

from __future__ import annotations

import json
from typing import Any

_ALLOWED_FIELDS = frozenset({"title", "author"})


class NotFound(Exception):
    """Raised when a record id does not exist in the catalog."""


class Catalog:
    def __init__(self) -> None:
        # dict preserves insertion order, which gives list() creation order.
        self._records: dict[str, dict[str, str]] = {}
        # Tags live beside the records so get()/list() keep their fixed shape.
        self._tags: dict[str, set[str]] = {}
        self._next_id: int = 1

    def _require(self, record_id: str) -> dict[str, str]:
        try:
            return self._records[record_id]
        except KeyError:
            raise NotFound(record_id) from None

    def create(self, title: str, author: str) -> str:
        record_id = str(self._next_id)
        self._next_id += 1
        self._records[record_id] = {"id": record_id, "title": title, "author": author}
        return record_id

    def get(self, record_id: str) -> dict:
        return dict(self._require(record_id))

    def update(self, record_id: str, **fields: Any) -> dict:
        record = self._require(record_id)
        unknown = set(fields) - _ALLOWED_FIELDS
        if unknown:
            raise ValueError(f"unknown field(s): {', '.join(sorted(unknown))}")
        record.update(fields)
        return dict(record)

    def delete(self, record_id: str) -> None:
        self._require(record_id)
        del self._records[record_id]
        self._tags.pop(record_id, None)

    def clone(self, record_id: str) -> str:
        """Create a new record with the same title and author; returns the new id. NotFound."""
        record = self._require(record_id)
        return self.create(record["title"], record["author"])

    def bulk_create(self, items: list[tuple[str, str]]) -> list[str]:
        """Create one record per (title, author) pair; returns the new ids in order."""
        return [self.create(title, author) for title, author in items]

    def count(self) -> int:
        return len(self._records)

    def list(self) -> list[dict]:
        return [dict(r) for r in self._records.values()]

    def find(self, substring: str) -> list[dict]:
        """Records whose title contains `substring` (case-insensitive), in creation order."""
        needle = substring.casefold()
        return [dict(r) for r in self._records.values() if needle in r["title"].casefold()]

    def tag(self, record_id: str, tag: str) -> None:
        """Attach `tag` to a record; a no-op if already present. NotFound."""
        self._require(record_id)
        self._tags.setdefault(record_id, set()).add(tag)

    def untag(self, record_id: str, tag: str) -> None:
        """Remove `tag` from a record; a no-op if not present. NotFound."""
        self._require(record_id)
        tags = self._tags.get(record_id)
        if tags is not None:
            tags.discard(tag)
            if not tags:
                del self._tags[record_id]

    def tags(self, record_id: str) -> list[str]:
        """Sorted tags of a record. NotFound."""
        self._require(record_id)
        return sorted(self._tags.get(record_id, ()))

    def by_tag(self, tag: str) -> list[dict]:
        """Records carrying `tag`, in creation order."""
        return [dict(r) for rid, r in self._records.items() if tag in self._tags.get(rid, ())]

    def export(self) -> str:
        """JSON array of all records in creation order, each with a sorted "tags" list."""
        return json.dumps([{**r, "tags": self.tags(r["id"])} for r in self._records.values()])

    def import_(self, dump: str) -> None:
        """Load records from an export() dump, keeping their ids.

        Works on an empty or existing catalog. Raises ValueError if the dump is
        malformed or if any id in the dump already exists in this catalog; in
        that case nothing is imported. The id counter is advanced past any
        numeric imported id so later create() calls never collide with them.
        """
        data = json.loads(dump)
        if not isinstance(data, list):
            raise ValueError("dump must be a JSON array of records")
        incoming: dict[str, dict[str, str]] = {}
        incoming_tags: dict[str, set[str]] = {}
        for item in data:
            if not isinstance(item, dict) or set(item) - {"tags"} != {"id", "title", "author"}:
                raise ValueError(f"malformed record: {item!r}")
            if not all(isinstance(item[k], str) for k in ("id", "title", "author")):
                raise ValueError(f"malformed record: {item!r}")
            # "tags" is optional so dumps made before tags existed still load.
            tags = item.get("tags", [])
            if not isinstance(tags, list) or not all(isinstance(t, str) for t in tags):
                raise ValueError(f"malformed record: {item!r}")
            record_id = item["id"]
            if record_id in incoming or record_id in self._records:
                raise ValueError(f"duplicate id: {record_id}")
            incoming[record_id] = {"id": record_id, "title": item["title"], "author": item["author"]}
            if tags:
                incoming_tags[record_id] = set(tags)
        self._records.update(incoming)
        self._tags.update(incoming_tags)
        for record_id in incoming:
            if record_id.isdigit():
                self._next_id = max(self._next_id, int(record_id) + 1)
