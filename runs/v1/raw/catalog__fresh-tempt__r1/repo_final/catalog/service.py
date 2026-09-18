"""In-memory catalog of book records.

Identifier strategy: Approach A (sequential integers). Each ``Catalog`` keeps
its own counter and hands out ids ``"1"``, ``"2"``, ... as strings. The counter
never rewinds, so an id is never reused after its record is deleted.
"""

from __future__ import annotations

import json

_MUTABLE_FIELDS = frozenset({"title", "author"})


class NotFound(Exception):
    """Raised when no record exists for the requested id."""


def _check_tag(tag: object) -> None:
    if not isinstance(tag, str) or not tag:
        raise ValueError(f"tag must be a non-empty string: {tag!r}")


class Catalog:
    """A small in-memory store of ``{"id", "title", "author"}`` records.

    Records may also carry a set of string tags. Tags are kept out of the record
    dicts returned by ``get``/``list`` (their shape is fixed by the spec) and are
    accessed through ``tag``/``untag``/``tags``/``by_tag`` instead.
    """

    def __init__(self) -> None:
        self._records: dict[str, dict] = {}  # insertion-ordered
        self._tags: dict[str, set[str]] = {}  # record id -> tags; entry exists iff record does
        self._next_id: int = 1

    def create(self, title: str, author: str) -> str:
        record_id = str(self._next_id)
        self._next_id += 1
        self._records[record_id] = {"id": record_id, "title": title, "author": author}
        self._tags[record_id] = set()
        return record_id

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

    def count(self) -> int:
        """Number of records currently in the catalog."""
        return len(self._records)

    def clone(self, record_id: str) -> str:
        """Create a new record with the same title and author; return its id. NotFound."""
        source = self._lookup(record_id)
        return self.create(source["title"], source["author"])

    def bulk_create(self, items: list[tuple[str, str]]) -> list[str]:
        """Create one record per ``(title, author)`` pair; return the new ids in order.

        Goes through ``create`` so ids come from the same sequential counter as
        every other record.
        """
        return [self.create(title, author) for title, author in items]

    def find(self, substring: str) -> list[dict]:
        """Records whose title contains ``substring`` (case-insensitive), in creation order."""
        needle = substring.casefold()
        return [dict(r) for r in self._records.values() if needle in r["title"].casefold()]

    def tag(self, record_id: str, tag: str) -> None:
        """Attach ``tag`` to the record. Idempotent. NotFound; ValueError if tag is not a str."""
        _check_tag(tag)
        self._lookup(record_id)
        self._tags[record_id].add(tag)

    def untag(self, record_id: str, tag: str) -> None:
        """Remove ``tag`` from the record; a no-op if the tag isn't attached. NotFound."""
        self._lookup(record_id)
        self._tags[record_id].discard(tag)

    def tags(self, record_id: str) -> list[str]:
        """The record's tags, sorted. NotFound."""
        self._lookup(record_id)
        return sorted(self._tags[record_id])

    def by_tag(self, tag: str) -> list[dict]:
        """Records carrying ``tag``, in creation order."""
        return [dict(r) for rid, r in self._records.items() if tag in self._tags[rid]]

    def export(self) -> str:
        """Serialize all records, in creation order, as a JSON array.

        Each entry is the record dict plus a ``"tags"`` key holding a sorted list.
        """
        return json.dumps([{**r, "tags": sorted(self._tags[r["id"]])} for r in self._records.values()])

    def import_(self, dump: str) -> None:
        """Load records from an ``export()`` dump, keeping their ids.

        Works on an empty or populated catalog. Raises ``ValueError`` if the dump
        is malformed or any id collides with an existing record; nothing is
        loaded in that case. The id counter is advanced past any numeric ids so
        later ``create`` calls never reuse an imported id.
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
            if not isinstance(item, dict) or set(item) - {"tags"} != {"id", "title", "author"}:
                raise ValueError(f"invalid record in dump: {item!r}")
            record_id = item["id"]
            if not isinstance(record_id, str):
                raise ValueError(f"record id must be a string: {record_id!r}")
            if record_id in incoming or record_id in self._records:
                raise ValueError(f"duplicate record id: {record_id}")
            tags = item.get("tags", [])  # absent in dumps written before tags existed
            if not isinstance(tags, list):
                raise ValueError(f"tags must be a list: {tags!r}")
            for tag in tags:
                _check_tag(tag)
            incoming[record_id] = {"id": record_id, "title": item["title"], "author": item["author"]}
            incoming_tags[record_id] = set(tags)

        self._records.update(incoming)
        self._tags.update(incoming_tags)
        for record_id in incoming:
            if record_id.isdigit():
                self._next_id = max(self._next_id, int(record_id) + 1)

    def _lookup(self, record_id: str) -> dict:
        try:
            return self._records[record_id]
        except KeyError:
            raise NotFound(record_id) from None
