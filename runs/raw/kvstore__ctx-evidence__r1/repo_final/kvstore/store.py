"""Persistent key-value store backed by a single human-readable JSON file.

Design (SPEC.md "Approach A"): the whole store is one JSON object on disk of
the form ``{namespace: {key: value}}``, written with two-space indentation,
sorted keys, and real Unicode characters (no ``\\uXXXX`` escapes). That layout
is what makes the file editable by hand and gives line-oriented diffs in code
review: each key/value pair sits on its own line.

The store is small and single-process, so the data is held in memory and the
file is rewritten atomically (write to a temporary file in the same directory,
then ``os.replace`` over the target) after every mutation. Reads never touch
the disk after ``__init__``.

Files created by the earlier SQLite-backed version of this module are
converted to the JSON layout the first time they are opened.
"""

from __future__ import annotations

import json
import os
import sqlite3
import tempfile

DEFAULT_NS = "default"

_SQLITE_MAGIC = b"SQLite format 3\x00"

Data = dict[str, dict[str, str]]


class Store:
    """A tiny persistent mapping of (namespace, key) -> value in one JSON file."""

    def __init__(self, path: str) -> None:
        self._path = path
        self._closed = False
        self._data: Data = self._load()
        if not os.path.exists(path):
            self._flush()

    # -- persistence --------------------------------------------------------

    def _load(self) -> Data:
        try:
            with open(self._path, "rb") as fh:
                head = fh.read(len(_SQLITE_MAGIC))
        except FileNotFoundError:
            return {}

        if head == _SQLITE_MAGIC:
            data = self._read_legacy_sqlite()
            # Rewrite immediately so the file is text from now on.
            self._data = data
            self._flush()
            return data

        with open(self._path, "r", encoding="utf-8") as fh:
            text = fh.read()
        if not text.strip():
            return {}
        raw = json.loads(text)
        return _validate(raw, source=self._path)

    def _read_legacy_sqlite(self) -> Data:
        conn = sqlite3.connect(self._path)
        try:
            columns = {row[1] for row in conn.execute("PRAGMA table_info(kv)")}
            if not columns:
                return {}
            if "ns" in columns:
                rows = conn.execute("SELECT ns, key, value FROM kv").fetchall()
            else:
                rows = [
                    (DEFAULT_NS, k, v)
                    for k, v in conn.execute("SELECT key, value FROM kv")
                ]
        finally:
            conn.close()
        data: Data = {}
        for ns, key, value in rows:
            data.setdefault(ns, {})[key] = value
        return data

    def _flush(self) -> None:
        """Atomically rewrite the data file from the in-memory state."""
        directory = os.path.dirname(os.path.abspath(self._path))
        text = _dumps(self._data)
        fd, tmp = tempfile.mkstemp(prefix=".kvstore-", suffix=".tmp", dir=directory)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(text)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, self._path)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    def _check_open(self) -> None:
        if self._closed:
            raise ValueError("Store is closed")

    # -- public API ---------------------------------------------------------

    def set(self, key: str, value: str, ns: str = DEFAULT_NS) -> None:
        self._check_open()
        self._data.setdefault(ns, {})[key] = value
        self._flush()

    def get(self, key: str, ns: str = DEFAULT_NS) -> str | None:
        self._check_open()
        return self._data.get(ns, {}).get(key)

    def delete(self, key: str, ns: str = DEFAULT_NS) -> bool:
        self._check_open()
        bucket = self._data.get(ns)
        if bucket is None or key not in bucket:
            return False
        del bucket[key]
        if not bucket:
            del self._data[ns]
        self._flush()
        return True

    def keys(self, ns: str = DEFAULT_NS) -> list[str]:
        self._check_open()
        return sorted(self._data.get(ns, {}))

    def count(self, ns: str = DEFAULT_NS) -> int:
        self._check_open()
        return len(self._data.get(ns, {}))

    def namespaces(self) -> list[str]:
        """Sorted names of namespaces that currently hold at least one key."""
        self._check_open()
        return sorted(ns for ns, bucket in self._data.items() if bucket)

    def items(self, ns: str = DEFAULT_NS) -> list[tuple[str, str]]:
        """All ``(key, value)`` pairs in ``ns``, sorted by key."""
        self._check_open()
        return sorted(self._data.get(ns, {}).items())

    def rename(self, old: str, new: str, ns: str = DEFAULT_NS) -> bool:
        """Move the value at ``old`` to ``new`` within ``ns``.

        Any existing value at ``new`` is overwritten. Returns ``False`` (and
        changes nothing) if ``old`` is not present.
        """
        self._check_open()
        bucket = self._data.get(ns)
        if bucket is None or old not in bucket:
            return False
        if old == new:
            return True
        bucket[new] = bucket.pop(old)
        self._flush()
        return True

    def search(self, substring: str, ns: str = DEFAULT_NS) -> list[str]:
        """Sorted keys in ``ns`` that contain ``substring`` (case-sensitive)."""
        self._check_open()
        return sorted(k for k in self._data.get(ns, {}) if substring in k)

    def export_json(self, path: str) -> None:
        """Write the whole store to ``path`` as ``{namespace: {key: value}}``."""
        self._check_open()
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(_dumps(self._data))

    def import_json(self, path: str) -> None:
        """Merge a ``{namespace: {key: value}}`` file into the store.

        Existing keys are overwritten by the imported values; keys not present
        in the file are left untouched.
        """
        self._check_open()
        with open(path, "r", encoding="utf-8") as fh:
            raw = json.load(fh)
        incoming = _validate(raw, source=path)
        for ns, bucket in incoming.items():
            if bucket:
                self._data.setdefault(ns, {}).update(bucket)
        self._flush()

    def close(self) -> None:
        self._closed = True

    # -- conveniences -------------------------------------------------------

    def __enter__(self) -> "Store":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def __repr__(self) -> str:
        state = "closed" if self._closed else "open"
        return f"Store({self._path!r}, {state})"


# -- helpers ----------------------------------------------------------------


def _dumps(data: Data) -> str:
    # Drop empty namespaces so the file only lists namespaces that hold keys.
    payload = {ns: bucket for ns, bucket in data.items() if bucket}
    return json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def _validate(raw: object, *, source: str) -> Data:
    """Check that ``raw`` has the ``{str: {str: str}}`` shape and copy it."""
    if not isinstance(raw, dict):
        raise ValueError(f"{source}: top level must be a JSON object")
    data: Data = {}
    for ns, bucket in raw.items():
        if not isinstance(bucket, dict):
            raise ValueError(f"{source}: namespace {ns!r} must map to an object")
        for key, value in bucket.items():
            if not isinstance(value, str):
                raise ValueError(
                    f"{source}: value for {ns!r}/{key!r} must be a string"
                )
        data[ns] = dict(bucket)
    return data
