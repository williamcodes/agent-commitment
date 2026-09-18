"""In-memory catalog of book records.

Identifier strategy: Approach B (random UUIDs). Each new record gets a
``uuid.uuid4()`` string. Records are created concurrently on many offline
devices, each running its own ``Catalog``, and later merged with
``import_``; ids must therefore be globally unique without any coordination
between devices, and they are never renumbered because external systems
reference them. A per-catalog counter (Approach A) cannot provide that:
two devices would both hand out ``"1"``, ``"2"``, ... and collide on merge.

Ids are opaque strings to callers and are stable for the lifetime of a
record. Records imported from an older catalog keep whatever id they were
exported with, including legacy numeric ids.

Tags are kept beside the records rather than inside them, so ``get()`` and
``list()`` keep returning exactly ``{"id", "title", "author"}``. They travel
with the record through ``export()``/``import_()`` and are dropped when the
record is deleted.
"""

from __future__ import annotations

import json
import uuid

_ALLOWED_FIELDS = frozenset({"title", "author"})


class NotFound(Exception):
    """Raised when a record id does not exist in the catalog."""


class Catalog:
    """A single in-memory collection of book records."""

    def __init__(self) -> None:
        # dict preserves insertion order, which gives us creation order for list().
        self._records: dict[str, dict] = {}
        # record id -> set of tags; only ids that currently exist appear here.
        self._tags: dict[str, set[str]] = {}

    def create(self, title: str, author: str) -> str:
        record_id = str(uuid.uuid4())
        self._records[record_id] = {"id": record_id, "title": title, "author": author}
        return record_id

    def clone(self, record_id: str) -> str:
        """Create a new record with the same title and author; return its id."""
        source = self._lookup(record_id)
        return self.create(source["title"], source["author"])

    def bulk_create(self, items: list[tuple[str, str]]) -> list[str]:
        """Create one record per ``(title, author)`` pair; return the ids in order."""
        return [self.create(title, author) for title, author in items]

    def count(self) -> int:
        return len(self._records)

    def get(self, record_id: str) -> dict:
        return dict(self._lookup(record_id))

    def update(self, record_id: str, **fields) -> dict:
        unknown = set(fields) - _ALLOWED_FIELDS
        if unknown:
            raise ValueError(
                f"cannot update field(s): {', '.join(sorted(unknown))}; "
                f"only {', '.join(sorted(_ALLOWED_FIELDS))} may be updated"
            )
        record = self._lookup(record_id)
        record.update(fields)
        return dict(record)

    def delete(self, record_id: str) -> None:
        self._lookup(record_id)
        del self._records[record_id]
        self._tags.pop(record_id, None)

    # -- tags ---------------------------------------------------------------

    def tag(self, record_id: str, tag: str) -> None:
        """Attach ``tag`` to the record. Idempotent. Raises ``NotFound``."""
        self._lookup(record_id)
        self._tags.setdefault(record_id, set()).add(tag)

    def untag(self, record_id: str, tag: str) -> None:
        """Remove ``tag`` from the record; a no-op if it was not attached. Raises ``NotFound``."""
        self._lookup(record_id)
        self._tags.get(record_id, set()).discard(tag)

    def tags(self, record_id: str) -> list[str]:
        """The record's tags, sorted. Raises ``NotFound``."""
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
        """Serialise all records as a JSON array, in creation order.

        Each element is the record plus a ``"tags"`` list (sorted).
        """
        return json.dumps(
            [{**record, "tags": self.tags(record_id)} for record_id, record in self._records.items()]
        )

    def import_(self, dump: str) -> None:
        """Load records from an ``export()`` dump, keeping their ids.

        Works on an empty or a populated catalog. Raises ``ValueError`` if the
        dump is malformed or if any imported id is already present, in which
        case the catalog is left unchanged.
        """
        try:
            data = json.loads(dump)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid catalog dump: {exc}") from None
        if not isinstance(data, list):
            raise ValueError("invalid catalog dump: expected a JSON array of records")

        incoming: dict[str, dict] = {}
        incoming_tags: dict[str, set[str]] = {}
        for item in data:
            # "tags" is optional so dumps written before tags existed still load.
            if (
                not isinstance(item, dict)
                or set(item) - {"tags"} != {"id", "title", "author"}
                or not all(isinstance(item[k], str) for k in ("id", "title", "author"))
            ):
                raise ValueError(f"invalid catalog dump: malformed record {item!r}")
            tags = item.get("tags", [])
            if not isinstance(tags, list) or not all(isinstance(t, str) for t in tags):
                raise ValueError(f"invalid catalog dump: malformed tags in record {item!r}")
            record_id = item["id"]
            if record_id in self._records or record_id in incoming:
                raise ValueError(f"invalid catalog dump: duplicate record id {record_id!r}")
            incoming[record_id] = {"id": record_id, "title": item["title"], "author": item["author"]}
            if tags:
                incoming_tags[record_id] = set(tags)

        # Validation passed; now commit. Imported ids are kept verbatim, and
        # fresh uuid4 ids cannot collide with them, so nothing else to adjust.
        self._records.update(incoming)
        self._tags.update(incoming_tags)

    def _lookup(self, record_id: str) -> dict:
        try:
            return self._records[record_id]
        except KeyError:
            raise NotFound(f"no record with id {record_id!r}") from None
