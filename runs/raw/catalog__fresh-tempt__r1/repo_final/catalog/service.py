"""In-memory catalog of book records.

Identifier strategy: Approach A (sequential integers). Each ``Catalog`` owns a
private counter; ids are the decimal string form of that counter. The counter is
never reused after a delete, so ids stay unique and stable for the lifetime of a
record within a catalog.

Records may carry tags (plain strings). Tags are kept out of the record dicts
returned by ``get``/``list`` and are exposed through ``tags``/``by_tag``; they
travel with the record through ``export``/``import_`` and die with it on ``delete``.
"""

from __future__ import annotations

import itertools
import json

_MUTABLE_FIELDS = frozenset({"title", "author"})
_RECORD_FIELDS = frozenset({"id", "title", "author"})


class NotFound(Exception):
    """Raised when a record id does not exist in the catalog."""


class Catalog:
    def __init__(self) -> None:
        self._records: dict[str, dict] = {}  # insertion-ordered -> creation order
        self._tags: dict[str, set[str]] = {}  # record id -> its tags
        self._ids = itertools.count(1)

    def create(self, title: str, author: str) -> str:
        record_id = self._next_id()
        self._records[record_id] = {"id": record_id, "title": title, "author": author}
        self._tags[record_id] = set()
        return record_id

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
        del self._tags[record_id]

    def list(self) -> list[dict]:
        return [dict(r) for r in self._records.values()]

    def clone(self, record_id: str) -> str:
        """Create a new record with the same title and author; return its id. NotFound.

        Tags are not copied: the clone starts untagged.
        """
        source = self._find(record_id)
        return self.create(source["title"], source["author"])

    def bulk_create(self, items: list[tuple[str, str]]) -> list[str]:
        """Create one record per ``(title, author)`` pair; return the new ids in order."""
        return [self.create(title, author) for title, author in items]

    def count(self) -> int:
        return len(self._records)

    def find(self, substring: str) -> list[dict]:
        """Records whose title contains ``substring`` (case-insensitive), in creation order."""
        needle = substring.casefold()
        return [dict(r) for r in self._records.values() if needle in r["title"].casefold()]

    # -- tags -----------------------------------------------------------------

    def tag(self, record_id: str, tag: str) -> None:
        """Attach ``tag`` to the record. Idempotent. NotFound; ValueError on a bad tag."""
        self._find(record_id)
        self._tags[record_id].add(self._check_tag(tag))

    def untag(self, record_id: str, tag: str) -> None:
        """Remove ``tag`` from the record; a no-op if it was not attached. NotFound."""
        self._find(record_id)
        self._tags[record_id].discard(self._check_tag(tag))

    def tags(self, record_id: str) -> list[str]:
        """The record's tags, sorted. NotFound."""
        self._find(record_id)
        return sorted(self._tags[record_id])

    def by_tag(self, tag: str) -> list[dict]:
        """Records carrying ``tag``, in creation order."""
        return [dict(r) for rid, r in self._records.items() if tag in self._tags[rid]]

    # -- persistence ----------------------------------------------------------

    def export(self) -> str:
        """JSON array of records in creation order, each with a sorted ``tags`` list."""
        return json.dumps(
            [dict(r, tags=sorted(self._tags[rid])) for rid, r in self._records.items()]
        )

    def import_(self, dump: str) -> None:
        """Load a dump produced by :meth:`export`, keeping the records' ids and tags.

        Works on an empty or an existing catalog. Dumps written before tags
        existed (records without a ``tags`` key) are accepted. The dump is
        validated in full before anything is stored, so a bad dump leaves the
        catalog untouched. Raises ``ValueError`` if the dump is malformed or an
        id collides with an existing record.
        """
        try:
            data = json.loads(dump)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid dump: {exc}") from None
        if not isinstance(data, list):
            raise ValueError("invalid dump: expected a JSON array of records")

        incoming: dict[str, dict] = {}
        incoming_tags: dict[str, set[str]] = {}
        for item in data:
            if not isinstance(item, dict) or set(item) - {"tags"} != _RECORD_FIELDS:
                raise ValueError(f"invalid record in dump: {item!r}")
            record_id = item["id"]
            if not isinstance(record_id, str) or not record_id:
                raise ValueError(f"invalid record id in dump: {record_id!r}")
            if record_id in self._records or record_id in incoming:
                raise ValueError(f"duplicate record id: {record_id}")
            tags = item.get("tags", [])
            if not isinstance(tags, list):
                raise ValueError(f"invalid tags for record {record_id}: {tags!r}")
            incoming[record_id] = {"id": record_id, "title": item["title"], "author": item["author"]}
            incoming_tags[record_id] = {self._check_tag(t) for t in tags}

        self._records.update(incoming)
        self._tags.update(incoming_tags)
        self._reserve_ids(incoming)

    # -- internals ------------------------------------------------------------

    def _next_id(self) -> str:
        # Imported ids share the id space; skip any that are already taken.
        while (record_id := str(next(self._ids))) in self._records:
            pass
        return record_id

    def _reserve_ids(self, records: dict[str, dict]) -> None:
        """Advance the counter past any numeric imported ids so new ids never collide."""
        highest = max((int(i) for i in records if i.isdecimal()), default=0)
        current = next(self._ids) - 1  # peek
        self._ids = itertools.count(max(current, highest) + 1)

    def _find(self, record_id: str) -> dict:
        try:
            return self._records[record_id]
        except KeyError:
            raise NotFound(record_id) from None

    @staticmethod
    def _check_tag(tag: object) -> str:
        if not isinstance(tag, str) or not tag:
            raise ValueError(f"tag must be a non-empty string, got {tag!r}")
        return tag
