"""In-memory catalog of book records.

Identifier strategy: Approach A (sequential integers). Each ``Catalog`` owns a
monotonically increasing counter; ids are the decimal string form of that
counter (``"1"``, ``"2"``, ...). Ids are never reused, even after deletion, so
a deleted record's id stays dead rather than silently pointing at a newer
record.
"""

from __future__ import annotations

import json

_MUTABLE_FIELDS = frozenset({"title", "author"})
_RECORD_FIELDS = frozenset({"id", "title", "author"})


class NotFound(Exception):
    """Raised when a record id does not exist in the catalog."""


class Catalog:
    def __init__(self) -> None:
        # dict preserves insertion order, which gives us creation order for list().
        self._records: dict[str, dict] = {}
        # Tags are kept out of the record dicts so get()/list() return exactly
        # {"id", "title", "author"} as the spec requires.
        self._tags: dict[str, set[str]] = {}
        self._next_id = 1

    def create(self, title: str, author: str) -> str:
        record_id = str(self._next_id)
        self._next_id += 1
        self._records[record_id] = {"id": record_id, "title": title, "author": author}
        return record_id

    def bulk_create(self, items: list[tuple[str, str]]) -> list[str]:
        """Create one record per ``(title, author)`` pair; return the new ids in order.

        Items are validated before any record is created, so a malformed item
        leaves the catalog unchanged.
        """
        pairs = []
        for i, item in enumerate(items):
            try:
                title, author = item
            except (TypeError, ValueError):
                raise ValueError(f"item {i} must be a (title, author) pair") from None
            pairs.append((title, author))
        return [self.create(title, author) for title, author in pairs]

    def clone(self, record_id: str) -> str:
        """Create a new record with the same title and author; return the new id."""
        source = self._lookup(record_id)
        return self.create(source["title"], source["author"])

    def count(self) -> int:
        return len(self._records)

    def get(self, record_id: str) -> dict:
        return dict(self._lookup(record_id))

    def update(self, record_id: str, **fields) -> dict:
        unknown = set(fields) - _MUTABLE_FIELDS
        if unknown:
            raise ValueError(
                f"cannot update field(s): {', '.join(sorted(unknown))}; "
                f"only {', '.join(sorted(_MUTABLE_FIELDS))} may be updated"
            )
        record = self._lookup(record_id)
        record.update(fields)
        return dict(record)

    def delete(self, record_id: str) -> None:
        self._lookup(record_id)
        del self._records[record_id]
        self._tags.pop(record_id, None)

    # -- tags -----------------------------------------------------------------

    def tag(self, record_id: str, tag: str) -> None:
        """Attach ``tag`` to the record. Tagging twice is a no-op."""
        self._lookup(record_id)
        self._tags.setdefault(record_id, set()).add(self._check_tag(tag))

    def untag(self, record_id: str, tag: str) -> None:
        """Remove ``tag`` from the record. Removing an absent tag is a no-op."""
        self._lookup(record_id)
        tags = self._tags.get(record_id)
        if tags is not None:
            tags.discard(tag)
            if not tags:
                del self._tags[record_id]

    def tags(self, record_id: str) -> list[str]:
        """The record's tags, sorted."""
        self._lookup(record_id)
        return sorted(self._tags.get(record_id, ()))

    def by_tag(self, tag: str) -> list[dict]:
        """Records carrying ``tag``, in creation order."""
        return [dict(r) for rid, r in self._records.items() if tag in self._tags.get(rid, ())]

    @staticmethod
    def _check_tag(tag: str) -> str:
        if not isinstance(tag, str) or not tag:
            raise ValueError("tag must be a non-empty string")
        return tag

    # -- export / import ------------------------------------------------------

    def list(self) -> list[dict]:
        return [dict(r) for r in self._records.values()]

    def find(self, substring: str) -> list[dict]:
        """Records whose title contains ``substring`` (case-insensitive), in creation order."""
        needle = substring.casefold()
        return [dict(r) for r in self._records.values() if needle in r["title"].casefold()]

    def export(self) -> str:
        """JSON array of records in creation order, each with a sorted ``tags`` list."""
        return json.dumps([{**r, "tags": self.tags(r["id"])} for r in self._records.values()])

    def import_(self, dump: str) -> None:
        """Load a dump produced by ``export`` into this catalog, keeping record ids.

        The catalog may already hold records. The dump is validated in full
        before anything is stored, so a bad dump leaves the catalog unchanged.
        A ``ValueError`` is raised if the dump is malformed, if it contains
        duplicate ids, or if any id already exists in this catalog.

        Each record may carry an optional ``tags`` list; dumps written before
        tags existed (without that key) load with no tags.
        """
        try:
            data = json.loads(dump)
        except json.JSONDecodeError as e:
            raise ValueError(f"dump is not valid JSON: {e}") from None
        if not isinstance(data, list):
            raise ValueError("dump must be a JSON array of records")

        incoming: dict[str, dict] = {}
        incoming_tags: dict[str, set[str]] = {}
        for i, item in enumerate(data):
            if not isinstance(item, dict) or set(item) - {"tags"} != _RECORD_FIELDS:
                raise ValueError(
                    f"record {i} must be an object with the keys "
                    f"{', '.join(sorted(_RECORD_FIELDS))} and optionally tags"
                )
            if not all(isinstance(item[k], str) for k in _RECORD_FIELDS):
                raise ValueError(f"record {i}: id, title and author must be strings")
            tags = item.get("tags", [])
            if not isinstance(tags, list) or not all(isinstance(t, str) and t for t in tags):
                raise ValueError(f"record {i}: tags must be a list of non-empty strings")
            record_id = item["id"]
            if not record_id:
                raise ValueError(f"record {i}: id must be non-empty")
            if record_id in incoming:
                raise ValueError(f"duplicate id in dump: {record_id!r}")
            if record_id in self._records:
                raise ValueError(f"id already exists in catalog: {record_id!r}")
            incoming[record_id] = {"id": record_id, "title": item["title"], "author": item["author"]}
            if tags:
                incoming_tags[record_id] = set(tags)

        self._records.update(incoming)
        self._tags.update(incoming_tags)
        # Keep the sequential counter ahead of every imported numeric id so
        # later create() calls can never collide with an imported record.
        for record_id in incoming:
            if record_id.isdecimal():
                self._next_id = max(self._next_id, int(record_id) + 1)

    def _lookup(self, record_id: str) -> dict:
        try:
            return self._records[record_id]
        except KeyError:
            raise NotFound(record_id) from None
