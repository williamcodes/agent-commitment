"""In-memory catalog of book records.

Identifier strategy: Approach B (random UUIDs). Records are created
concurrently on many offline devices, each running its own ``Catalog``, and
later merged into one via ``import_``. Ids must therefore be globally unique
without any coordination between devices, and they can never be renumbered
because external systems already reference them. A per-instance counter
cannot satisfy that (two devices would both mint "1"), so every id is a
``uuid.uuid4()`` string minted at creation time and kept for the record's
lifetime, including across export/import.
"""

from __future__ import annotations

import json
import uuid

_ALLOWED_FIELDS = frozenset({"title", "author"})


class NotFound(Exception):
    """Raised when a record id does not exist in the catalog."""


def _new_id() -> str:
    return str(uuid.uuid4())


class Catalog:
    def __init__(self) -> None:
        self._records: dict[str, dict] = {}  # insertion-ordered: creation order
        self._tags: dict[str, set[str]] = {}  # record id -> tags; keys mirror _records

    def create(self, title: str, author: str) -> str:
        record_id = _new_id()
        self._records[record_id] = {"id": record_id, "title": title, "author": author}
        self._tags[record_id] = set()
        return record_id

    def bulk_create(self, items: list[tuple[str, str]]) -> list[str]:
        """Create one record per ``(title, author)`` pair; return the new ids in order."""
        return [self.create(title, author) for title, author in items]

    def clone(self, record_id: str) -> str:
        """Create a new record with the same title and author; return its id."""
        source = self._lookup(record_id)
        return self.create(source["title"], source["author"])

    def get(self, record_id: str) -> dict:
        return dict(self._lookup(record_id))

    def update(self, record_id: str, **fields) -> dict:
        unknown = set(fields) - _ALLOWED_FIELDS
        if unknown:
            raise ValueError(f"cannot update field(s): {', '.join(sorted(unknown))}")
        record = self._lookup(record_id)
        record.update(fields)
        return dict(record)

    def delete(self, record_id: str) -> None:
        self._lookup(record_id)
        del self._records[record_id]
        del self._tags[record_id]

    def count(self) -> int:
        return len(self._records)

    def list(self) -> list[dict]:
        return [dict(r) for r in self._records.values()]

    def find(self, substring: str) -> list[dict]:
        """Records whose title contains ``substring`` (case-insensitive), in creation order."""
        needle = substring.casefold()
        return [dict(r) for r in self._records.values() if needle in r["title"].casefold()]

    # -- tags -----------------------------------------------------------------

    def tag(self, record_id: str, tag: str) -> None:
        """Attach ``tag`` to the record (no-op if already present). NotFound."""
        self._lookup(record_id)
        self._tags[record_id].add(tag)

    def untag(self, record_id: str, tag: str) -> None:
        """Remove ``tag`` from the record (no-op if absent). NotFound."""
        self._lookup(record_id)
        self._tags[record_id].discard(tag)

    def tags(self, record_id: str) -> list[str]:
        """The record's tags, sorted. NotFound."""
        self._lookup(record_id)
        return sorted(self._tags[record_id])

    def by_tag(self, tag: str) -> list[dict]:
        """Records carrying ``tag``, in creation order."""
        return [dict(r) for rid, r in self._records.items() if tag in self._tags[rid]]

    # -- export / import ------------------------------------------------------

    def export(self) -> str:
        """Serialize all records as a JSON array in creation order.

        Each entry is ``{"id", "title", "author", "tags"}`` with ``tags`` sorted.
        """
        return json.dumps([{**r, "tags": sorted(self._tags[rid])} for rid, r in self._records.items()])

    def import_(self, dump: str) -> None:
        """Load records from an ``export()`` dump, keeping their ids verbatim.

        This is the merge path for records created on other devices, so ids
        are never rewritten. Works on an empty or a populated catalog. Raises
        ValueError if the dump is malformed or an imported id collides with an
        existing record (which, with UUID ids, means the same record is being
        imported twice); the catalog is left unchanged in that case.
        """
        data = json.loads(dump)
        if not isinstance(data, list):
            raise ValueError("dump must be a JSON array of records")
        incoming: dict[str, dict] = {}
        incoming_tags: dict[str, set[str]] = {}
        for item in data:
            # ``tags`` is optional so dumps written before tags existed still load.
            if not isinstance(item, dict) or set(item) - {"tags"} != {"id", "title", "author"}:
                raise ValueError(f"malformed record: {item!r}")
            record_id = item["id"]
            if not isinstance(record_id, str) or not record_id:
                raise ValueError(f"invalid id: {record_id!r}")
            if record_id in incoming or record_id in self._records:
                raise ValueError(f"duplicate id: {record_id}")
            tags = item.get("tags", [])
            if not isinstance(tags, list) or not all(isinstance(t, str) for t in tags):
                raise ValueError(f"invalid tags for {record_id}: {tags!r}")
            incoming[record_id] = {"id": record_id, "title": item["title"], "author": item["author"]}
            incoming_tags[record_id] = set(tags)
        self._records.update(incoming)
        self._tags.update(incoming_tags)

    def _lookup(self, record_id: str) -> dict:
        try:
            return self._records[record_id]
        except KeyError:
            raise NotFound(record_id) from None
