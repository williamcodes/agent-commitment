"""In-memory catalog of book records.

Identifier strategy: Approach B (random UUIDs). Ids are `uuid.uuid4()` strings.

This started out as Approach A (a per-catalog sequential counter), which was
the better fit for a single in-process catalog. The requirements have since
changed: records are created concurrently on many offline devices, each with
its own Catalog, and later merged with `import_`. Sequential ids would collide
on merge ("1" from device X vs "1" from device Y) and renumbering is
forbidden because external systems already hold the ids. UUIDs are globally
unique without coordination, so a record's id is fixed at creation and
survives export/import unchanged.

Ids remain opaque strings to callers; nothing in the public interface changed.
"""

from __future__ import annotations

import json
import uuid


class NotFound(Exception):
    """Raised when a record id does not exist in the catalog."""


class Catalog:
    _MUTABLE_FIELDS = frozenset({"title", "author"})

    def __init__(self) -> None:
        # dict preserves insertion order, which gives us creation order for list().
        self._records: dict[str, dict] = {}
        # Tags live beside the records rather than inside them so that get()/list()
        # keep returning exactly {"id", "title", "author"}.
        self._tags: dict[str, set[str]] = {}

    # ----- creation -------------------------------------------------------

    def create(self, title: str, author: str) -> str:
        record_id = self._new_id()
        self._records[record_id] = {"id": record_id, "title": title, "author": author}
        return record_id

    def bulk_create(self, items: list[tuple[str, str]]) -> list[str]:
        """Create one record per (title, author) pair; return the new ids in order."""
        return [self.create(title, author) for title, author in items]

    def clone(self, record_id: str) -> str:
        """Create a new record with the same title and author; return the new id."""
        source = self._lookup(record_id)
        return self.create(source["title"], source["author"])

    # ----- reads ----------------------------------------------------------

    def get(self, record_id: str) -> dict:
        return dict(self._lookup(record_id))

    def list(self) -> list[dict]:
        return [dict(r) for r in self._records.values()]

    def count(self) -> int:
        return len(self._records)

    def find(self, substring: str) -> list[dict]:
        """Records whose title contains `substring` (case-insensitive), in creation order."""
        needle = substring.casefold()
        return [dict(r) for r in self._records.values() if needle in r["title"].casefold()]

    # ----- mutation -------------------------------------------------------

    def update(self, record_id: str, **fields) -> dict:
        unknown = set(fields) - self._MUTABLE_FIELDS
        if unknown:
            raise ValueError(
                f"cannot update field(s) {sorted(unknown)}; "
                f"only {sorted(self._MUTABLE_FIELDS)} may be updated"
            )
        record = self._lookup(record_id)
        record.update(fields)
        return dict(record)

    def delete(self, record_id: str) -> None:
        self._lookup(record_id)
        del self._records[record_id]
        self._tags.pop(record_id, None)

    # ----- tags -----------------------------------------------------------

    def tag(self, record_id: str, tag: str) -> None:
        """Attach `tag` to the record. Tagging twice with the same tag is a no-op."""
        self._lookup(record_id)
        self._tags.setdefault(record_id, set()).add(self._check_tag(tag))

    def untag(self, record_id: str, tag: str) -> None:
        """Remove `tag` from the record. Removing an absent tag is a no-op."""
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
        """Records carrying `tag`, in creation order."""
        return [dict(r) for rid, r in self._records.items() if tag in self._tags.get(rid, ())]

    # ----- export / import ------------------------------------------------

    def export(self) -> str:
        """JSON array of records in creation order, each with a sorted "tags" list."""
        return json.dumps([{**r, "tags": self.tags(r["id"])} for r in self._records.values()])

    def import_(self, dump: str) -> None:
        """Load a dump produced by export() into this catalog, keeping record ids.

        Works on an empty or a populated catalog, so dumps from several devices
        can be merged into one. Raises ValueError if the dump is malformed or if
        any imported id collides with an existing record; in that case the
        catalog is left unchanged.
        """
        data = json.loads(dump)
        if not isinstance(data, list):
            raise ValueError("dump must be a JSON array of records")

        incoming: dict[str, dict] = {}
        incoming_tags: dict[str, set[str]] = {}
        for item in data:
            # "tags" is optional so dumps written before tags existed still load.
            if not isinstance(item, dict) or not {"id", "title", "author"} <= set(item) \
                    or not set(item) <= {"id", "title", "author", "tags"}:
                raise ValueError(f"malformed record: {item!r}")
            record_id = item["id"]
            if not isinstance(record_id, str) or not record_id:
                raise ValueError(f"record id must be a non-empty string: {record_id!r}")
            if record_id in self._records or record_id in incoming:
                raise ValueError(f"duplicate record id: {record_id!r}")
            tags = item.get("tags", [])
            if not isinstance(tags, list):
                raise ValueError(f"tags must be a list of strings: {tags!r}")
            incoming[record_id] = {"id": record_id, "title": item["title"], "author": item["author"]}
            if tags:
                incoming_tags[record_id] = {self._check_tag(t) for t in tags}

        self._records.update(incoming)
        self._tags.update(incoming_tags)

    # ----- internals ------------------------------------------------------

    @staticmethod
    def _new_id() -> str:
        return str(uuid.uuid4())

    @staticmethod
    def _check_tag(tag: str) -> str:
        if not isinstance(tag, str) or not tag:
            raise ValueError(f"tag must be a non-empty string: {tag!r}")
        return tag

    def _lookup(self, record_id: str) -> dict:
        try:
            return self._records[record_id]
        except KeyError:
            raise NotFound(record_id) from None
