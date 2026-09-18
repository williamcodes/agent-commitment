"""In-memory catalog of book records.

Identifier strategy: Approach B (random UUIDs). Ids are ``uuid.uuid4()``
strings. Records are created concurrently on many offline devices, each
running its own ``Catalog``, and later merged into one catalog via
``import_``. UUIDs are globally unique without any coordination between
devices, so merged catalogs never collide, and ids are never renumbered
because external systems reference them.

History: this module originally used sequential integer ids (Approach A).
That was replaced when the offline-merge requirement arrived; two devices
with independent counters would both produce ``"1"``.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

_UPDATABLE_FIELDS = frozenset({"title", "author"})


class NotFound(Exception):
    """Raised when a record id does not exist in the catalog."""


class Catalog:
    def __init__(self) -> None:
        # dict preserves insertion order, which gives us creation order for list().
        self._records: dict[str, dict[str, str]] = {}
        # Tags are stored beside the records, not inside them, so get()/list()
        # keep returning exactly {"id", "title", "author"}.
        self._tags: dict[str, set[str]] = {}

    @staticmethod
    def _new_id() -> str:
        return str(uuid.uuid4())

    def _lookup(self, record_id: str) -> dict[str, str]:
        try:
            return self._records[record_id]
        except KeyError:
            raise NotFound(record_id) from None

    def create(self, title: str, author: str) -> str:
        record_id = self._new_id()
        self._records[record_id] = {"id": record_id, "title": title, "author": author}
        return record_id

    def bulk_create(self, items: list[tuple[str, str]]) -> list[str]:
        """Create one record per ``(title, author)`` pair; return the new ids in order."""
        return [self.create(title, author) for title, author in items]

    def clone(self, record_id: str) -> str:
        """Create a new record with the same title and author; return the new id."""
        source = self._lookup(record_id)
        return self.create(source["title"], source["author"])

    def count(self) -> int:
        return len(self._records)

    def get(self, record_id: str) -> dict:
        return dict(self._lookup(record_id))

    def update(self, record_id: str, **fields: Any) -> dict:
        unknown = set(fields) - _UPDATABLE_FIELDS
        if unknown:
            raise ValueError(
                f"cannot update field(s): {', '.join(sorted(unknown))}; "
                f"only {', '.join(sorted(_UPDATABLE_FIELDS))} may be updated"
            )
        record = self._lookup(record_id)
        record.update(fields)
        return dict(record)

    def delete(self, record_id: str) -> None:
        self._lookup(record_id)
        del self._records[record_id]
        self._tags.pop(record_id, None)

    # -- tags ---------------------------------------------------------------

    @staticmethod
    def _check_tag(tag: str) -> None:
        if not isinstance(tag, str) or not tag:
            raise ValueError("tag must be a non-empty string")

    def tag(self, record_id: str, tag: str) -> None:
        """Attach ``tag`` to the record. Adding an existing tag is a no-op."""
        self._check_tag(tag)
        self._lookup(record_id)
        self._tags.setdefault(record_id, set()).add(tag)

    def untag(self, record_id: str, tag: str) -> None:
        """Remove ``tag`` from the record. Removing an absent tag is a no-op."""
        self._check_tag(tag)
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
        return [
            dict(record)
            for record_id, record in self._records.items()
            if tag in self._tags.get(record_id, ())
        ]

    def list(self) -> list[dict]:
        return [dict(record) for record in self._records.values()]

    def find(self, substring: str) -> list[dict]:
        """Records whose title contains ``substring`` (case-insensitive), in creation order."""
        needle = substring.casefold()
        return [
            dict(record)
            for record in self._records.values()
            if needle in record["title"].casefold()
        ]

    def export(self) -> str:
        """JSON array of all records in creation order, each with a sorted ``tags`` list."""
        return json.dumps(
            [dict(record, tags=self.tags(record_id)) for record_id, record in self._records.items()]
        )

    def import_(self, dump: str) -> None:
        """Load records from an ``export()`` dump, keeping their ids.

        Works on an empty or populated catalog. The dump is validated in full
        before anything is inserted, so a bad dump leaves the catalog unchanged.
        Raises ValueError if the dump is malformed or if any id in the dump is
        already present in this catalog or repeated within the dump.
        """
        try:
            data = json.loads(dump)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid catalog dump: {exc}") from None
        if not isinstance(data, list):
            raise ValueError("invalid catalog dump: expected a JSON array of records")

        incoming: dict[str, dict[str, str]] = {}
        incoming_tags: dict[str, set[str]] = {}
        for index, item in enumerate(data):
            # "tags" is optional so dumps written before tags existed still import.
            if not isinstance(item, dict) or not (
                {"id", "title", "author"} <= set(item) <= {"id", "title", "author", "tags"}
            ):
                raise ValueError(
                    f"invalid catalog dump: record {index} must have the keys "
                    "id, title, author and optionally tags"
                )
            if not all(isinstance(item[key], str) for key in ("id", "title", "author")):
                raise ValueError(f"invalid catalog dump: record {index} fields must be strings")
            tags = item.get("tags", [])
            if not isinstance(tags, list) or not all(isinstance(t, str) and t for t in tags):
                raise ValueError(
                    f"invalid catalog dump: record {index} tags must be a list of non-empty strings"
                )
            record_id = item["id"]
            if not record_id:
                raise ValueError(f"invalid catalog dump: record {index} has an empty id")
            if record_id in incoming:
                raise ValueError(f"invalid catalog dump: duplicate id {record_id!r} in dump")
            if record_id in self._records:
                raise ValueError(f"cannot import: id {record_id!r} already exists in catalog")
            incoming[record_id] = {"id": record_id, "title": item["title"], "author": item["author"]}
            if tags:
                incoming_tags[record_id] = set(tags)

        self._records.update(incoming)
        self._tags.update(incoming_tags)
