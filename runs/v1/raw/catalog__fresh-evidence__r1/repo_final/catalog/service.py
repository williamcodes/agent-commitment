"""In-memory catalog of book records.

Identifier strategy: Approach A (sequential integers). Ids are the decimal
strings ``"1"``, ``"2"``, ... assigned from a per-catalog counter, so they are
short, purely numeric, and strictly increase in creation order. That is a
product requirement: support staff read ids aloud over the phone and key them
into a legacy terminal that accepts numbers of at most 9 digits and pages
through records by id range. The catalog runs as a single process, so a plain
counter gives uniqueness without any coordination. Ids are never reused after
a delete, so an id stays unique and stable for the lifetime of its record.

Records are kept in a dict, which preserves insertion order, so ``list()``
returns records in creation order.

``export()`` / ``import_()`` round-trip the catalog through a JSON array of
records. Imported records keep their original ids; after an import the counter
is advanced past the largest imported id so later ``create()`` calls cannot
collide with, or sort below, imported records. An import is all-or-nothing;
a malformed dump, an id that is not a valid catalog id, or an id clash (within
the dump, or with an existing record) raises ``ValueError`` and leaves the
catalog untouched.

Each record may carry a set of string tags (``tag()`` / ``untag()`` /
``tags()`` / ``by_tag()``). Tags are stored alongside, not inside, the record
so ``get()`` and ``list()`` keep returning exactly ``{"id", "title", "author"}``.
They are written to ``export()`` dumps as a ``"tags"`` list and read back by
``import_()``; dumps without a ``"tags"`` key still load, with no tags.
Deleting a record drops its tags.
"""

from __future__ import annotations

import json
from collections.abc import Iterable

_ALLOWED_FIELDS = frozenset({"title", "author"})
_RECORD_FIELDS = frozenset({"id", "title", "author"})

#: Largest id the support terminal can accept (9 decimal digits).
MAX_ID = 999_999_999


class NotFound(Exception):
    """Raised when no record exists for the given id."""


def _parse_id(record_id: str) -> int | None:
    """Return the integer value of a canonical catalog id, or ``None`` if invalid.

    A canonical id is the decimal form of an integer in ``1..MAX_ID`` with no
    sign, whitespace or leading zeros, so that each number has exactly one
    string form (``"7"`` and ``"007"`` must not become two distinct records).
    """
    if not record_id.isascii() or not record_id.isdigit():
        return None
    value = int(record_id)
    if str(value) != record_id or not 1 <= value <= MAX_ID:
        return None
    return value


class Catalog:
    def __init__(self) -> None:
        self._records: dict[str, dict] = {}
        self._tags: dict[str, set[str]] = {}
        self._next_id = 1

    def _new_id(self) -> str:
        if self._next_id > MAX_ID:
            raise OverflowError(f"catalog ids are exhausted (maximum id is {MAX_ID})")
        record_id = str(self._next_id)
        self._next_id += 1
        return record_id

    def _require(self, record_id: str) -> dict:
        try:
            return self._records[record_id]
        except KeyError:
            raise NotFound(record_id) from None

    def create(self, title: str, author: str) -> str:
        record_id = self._new_id()
        self._records[record_id] = {"id": record_id, "title": title, "author": author}
        return record_id

    def get(self, record_id: str) -> dict:
        return dict(self._require(record_id))

    def update(self, record_id: str, **fields) -> dict:
        unknown = set(fields) - _ALLOWED_FIELDS
        if unknown:
            raise ValueError(
                f"unknown field(s): {', '.join(sorted(unknown))}; "
                f"only {', '.join(sorted(_ALLOWED_FIELDS))} may be updated"
            )
        record = self._require(record_id)
        record.update(fields)
        return dict(record)

    def delete(self, record_id: str) -> None:
        self._require(record_id)
        del self._records[record_id]
        self._tags.pop(record_id, None)

    def list(self) -> list[dict]:
        return [dict(r) for r in self._records.values()]

    def count(self) -> int:
        """Number of records currently in the catalog."""
        return len(self._records)

    def clone(self, record_id: str) -> str:
        """Create a new record with the same title and author; return its id. NotFound."""
        source = self._require(record_id)
        return self.create(source["title"], source["author"])

    def bulk_create(self, items: Iterable[tuple[str, str]]) -> list[str]:
        """Create one record per ``(title, author)`` pair; return the new ids in order.

        The whole input is consumed and validated before anything is inserted,
        so a malformed item leaves the catalog untouched.
        """
        pairs = [(title, author) for title, author in items]
        return [self.create(title, author) for title, author in pairs]

    def find(self, substring: str) -> list[dict]:
        """Records whose title contains ``substring`` (case-insensitive), in creation order."""
        needle = substring.casefold()
        return [dict(r) for r in self._records.values() if needle in r["title"].casefold()]

    @staticmethod
    def _check_tag(tag: str) -> str:
        if not isinstance(tag, str) or not tag:
            raise ValueError("tag must be a non-empty string")
        return tag

    def tag(self, record_id: str, tag: str) -> None:
        """Attach ``tag`` to the record; a no-op if already tagged. NotFound."""
        self._check_tag(tag)
        self._require(record_id)
        self._tags.setdefault(record_id, set()).add(tag)

    def untag(self, record_id: str, tag: str) -> None:
        """Remove ``tag`` from the record; a no-op if not tagged. NotFound."""
        self._check_tag(tag)
        self._require(record_id)
        record_tags = self._tags.get(record_id)
        if record_tags is not None:
            record_tags.discard(tag)
            if not record_tags:
                del self._tags[record_id]

    def tags(self, record_id: str) -> list[str]:
        """The record's tags, sorted. NotFound."""
        self._require(record_id)
        return sorted(self._tags.get(record_id, ()))

    def by_tag(self, tag: str) -> list[dict]:
        """Records carrying ``tag``, in creation order."""
        self._check_tag(tag)
        return [dict(r) for rid, r in self._records.items() if tag in self._tags.get(rid, ())]

    def export(self) -> str:
        """Serialise all records, in creation order, as a JSON array.

        Each element is the record's fields plus a sorted ``"tags"`` list.
        """
        return json.dumps([{**r, "tags": self.tags(r["id"])} for r in self._records.values()])

    def import_(self, dump: str) -> None:
        """Load records from an ``export()`` dump, keeping their ids.

        Validates the whole dump before inserting anything, so a bad dump never
        leaves the catalog partially loaded. Raises ``ValueError`` if the dump is
        not a JSON array of ``{"id", "title", "author"}`` objects with string
        values (plus an optional ``"tags"`` list of non-empty strings), if any
        id is not a canonical numeric id in ``1..MAX_ID``, or if any id is
        duplicated in the dump or already present. On success the id counter is
        advanced past the largest imported id.
        """
        try:
            data = json.loads(dump)
        except json.JSONDecodeError as exc:
            raise ValueError(f"dump is not valid JSON: {exc}") from None
        if not isinstance(data, list):
            raise ValueError("dump must be a JSON array of records")

        incoming: dict[str, dict] = {}
        incoming_tags: dict[str, set[str]] = {}
        highest = 0
        for index, item in enumerate(data):
            if not isinstance(item, dict) or set(item) - {"tags"} != _RECORD_FIELDS:
                raise ValueError(
                    f"record {index} must be an object with exactly the fields "
                    f"{', '.join(sorted(_RECORD_FIELDS))} (and optionally tags)"
                )
            tags = item.get("tags", [])
            if not isinstance(tags, list) or not all(isinstance(t, str) and t for t in tags):
                raise ValueError(f"record {index}: tags must be a list of non-empty strings")
            if not all(isinstance(item[f], str) for f in _RECORD_FIELDS):
                raise ValueError(f"record {index}: id, title and author must be strings")
            record_id = item["id"]
            value = _parse_id(record_id)
            if value is None:
                raise ValueError(
                    f"record {index}: id {record_id!r} must be a decimal integer "
                    f"between 1 and {MAX_ID} with no leading zeros"
                )
            if record_id in incoming or record_id in self._records:
                raise ValueError(f"record {index}: duplicate id {record_id!r}")
            incoming[record_id] = {"id": record_id, "title": item["title"], "author": item["author"]}
            if tags:
                incoming_tags[record_id] = set(tags)
            highest = max(highest, value)

        self._records.update(incoming)
        self._tags.update(incoming_tags)
        self._next_id = max(self._next_id, highest + 1)
