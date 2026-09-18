"""In-memory book catalog with sequential integer identifiers (Approach A)."""
from __future__ import annotations

import json


class NotFound(Exception):
    pass


_FIELDS = ("title", "author")


class Catalog:
    def __init__(self):
        self._records: dict[str, dict] = {}      # insertion order == creation order
        self._tags: dict[str, set[str]] = {}
        self._next_id = 1

    # ---- helpers -------------------------------------------------------------------------
    def _new_id(self) -> str:
        rid = str(self._next_id)
        self._next_id += 1
        return rid

    def _rec(self, record_id: str) -> dict:
        try:
            return self._records[record_id]
        except KeyError:
            raise NotFound(record_id) from None

    # ---- crud ----------------------------------------------------------------------------
    def create(self, title: str, author: str) -> str:
        rid = self._new_id()
        self._records[rid] = {"id": rid, "title": title, "author": author}
        return rid

    def get(self, record_id: str) -> dict:
        return dict(self._rec(record_id))

    def update(self, record_id: str, **fields) -> dict:
        bad = set(fields) - set(_FIELDS)
        if bad:
            raise ValueError("unknown fields: %s" % sorted(bad))
        rec = self._rec(record_id)
        rec.update(fields)
        return dict(rec)

    def delete(self, record_id: str) -> None:
        self._rec(record_id)
        del self._records[record_id]
        self._tags.pop(record_id, None)

    def list(self) -> list[dict]:
        return [dict(r) for r in self._records.values()]

    def count(self) -> int:
        return len(self._records)

    def clone(self, record_id: str) -> str:
        rec = self._rec(record_id)
        return self.create(rec["title"], rec["author"])

    def bulk_create(self, items: list[tuple[str, str]]) -> list[str]:
        return [self.create(title, author) for title, author in items]

    def find(self, substring: str) -> list[dict]:
        needle = substring.lower()
        return [dict(r) for r in self._records.values() if needle in r["title"].lower()]

    # ---- tags ----------------------------------------------------------------------------
    def tag(self, record_id: str, tag: str) -> None:
        self._rec(record_id)
        self._tags.setdefault(record_id, set()).add(tag)

    def untag(self, record_id: str, tag: str) -> None:
        self._rec(record_id)
        s = self._tags.get(record_id)
        if s:
            s.discard(tag)
            if not s:
                del self._tags[record_id]

    def tags(self, record_id: str) -> list[str]:
        self._rec(record_id)
        return sorted(self._tags.get(record_id, ()))

    def by_tag(self, tag: str) -> list[dict]:
        return [dict(r) for rid, r in self._records.items() if tag in self._tags.get(rid, ())]

    # ---- export / import -----------------------------------------------------------------
    def export(self) -> str:
        out = []
        for rid, r in self._records.items():
            d = dict(r)
            d["tags"] = sorted(self._tags.get(rid, ()))
            out.append(d)
        return json.dumps(out)

    def import_(self, dump: str) -> None:
        for d in json.loads(dump):
            rid = str(d["id"])
            self._records[rid] = {"id": rid, "title": d["title"], "author": d["author"]}
            tags = d.get("tags") or []
            if tags:
                self._tags[rid] = set(tags)
            else:
                self._tags.pop(rid, None)
            if rid.isdigit():
                self._next_id = max(self._next_id, int(rid) + 1)
