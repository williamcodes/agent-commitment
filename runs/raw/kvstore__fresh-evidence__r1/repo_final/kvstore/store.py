"""JSON-backed persistent key-value store (Approach A) with namespaces.

The data file is a single UTF-8 JSON document of the form
``{namespace: {key: value}}``, written with two-space indentation and sorted
keys. That layout is deliberate: one key per line, deterministic ordering,
and non-ASCII text left unescaped, so the file is readable in any text
editor and a change to one key produces a one-line diff in code review.

The whole store is held in memory and the file is rewritten (atomically)
after every mutation. Stores are small and used by a single process, so the
simplicity is worth more than incremental writes would be.
"""

from __future__ import annotations

import json
import os
import sqlite3

DEFAULT_NS = "default"

_SQLITE_MAGIC = b"SQLite format 3\x00"


class Store:
    """A persistent, namespaced key-value store kept in a single JSON file."""

    def __init__(self, path: str):
        self._path = path
        self._data: dict[str, dict[str, str]] = self._load()
        if not os.path.exists(path):
            self._save()  # spec: the data file is created if missing

    # ------------------------------------------------------------------ I/O

    def _load(self) -> dict[str, dict[str, str]]:
        if not os.path.exists(self._path):
            return {}
        with open(self._path, "rb") as f:
            raw = f.read()
        if not raw.strip():
            return {}  # an empty or whitespace-only file is an empty store
        if raw.startswith(_SQLITE_MAGIC):
            data = self._read_legacy_sqlite()
            self._data = data
            self._save()  # upgrade the file in place to the text format
            return data
        data = json.loads(raw.decode("utf-8"))
        _validate(data)
        return data

    def _read_legacy_sqlite(self) -> dict[str, dict[str, str]]:
        """Read a data file written by the earlier SQLite-backed store.

        Handles both the namespaced ``kv(ns, key, value)`` table and the
        original ``kv(key, value)`` table, whose rows belong to "default".
        This is a one-time upgrade path; the file is rewritten as JSON.
        """
        data: dict[str, dict[str, str]] = {}
        conn = sqlite3.connect(self._path)
        try:
            cols = [row[1] for row in conn.execute("PRAGMA table_info(kv)")]
            if "ns" in cols:
                rows = conn.execute("SELECT ns, key, value FROM kv")
            elif cols:
                rows = (
                    (DEFAULT_NS, k, v)
                    for k, v in conn.execute("SELECT key, value FROM kv")
                )
            else:
                rows = ()
            for ns, key, value in rows:
                data.setdefault(ns, {})[key] = value
        finally:
            conn.close()
        return data

    def _save(self) -> None:
        # Write to a sibling temp file and rename over the target so a crash
        # mid-write can never leave a truncated data file behind.
        tmp = f"{self._path}.tmp"
        with open(tmp, "w", encoding="utf-8", newline="\n") as f:
            json.dump(self._data, f, indent=2, sort_keys=True, ensure_ascii=False)
            f.write("\n")
        os.replace(tmp, self._path)

    # ------------------------------------------------------------ core API

    def set(self, key: str, value: str, ns: str = DEFAULT_NS) -> None:
        self._data.setdefault(ns, {})[key] = value
        self._save()

    def get(self, key: str, ns: str = DEFAULT_NS) -> str | None:
        return self._data.get(ns, {}).get(key)

    def delete(self, key: str, ns: str = DEFAULT_NS) -> bool:
        bucket = self._data.get(ns)
        if bucket is None or key not in bucket:
            return False
        del bucket[key]
        if not bucket:
            del self._data[ns]  # namespaces exist only while they hold keys
        self._save()
        return True

    def keys(self, ns: str = DEFAULT_NS) -> list[str]:
        return sorted(self._data.get(ns, {}))

    def items(self, ns: str = DEFAULT_NS) -> list[tuple[str, str]]:
        """``(key, value)`` pairs in ``ns``, sorted by key."""
        return sorted(self._data.get(ns, {}).items())

    def rename(self, old: str, new: str, ns: str = DEFAULT_NS) -> bool:
        """Move the value at ``old`` to ``new`` within ``ns``.

        Any existing value at ``new`` is overwritten. Returns False (and
        changes nothing) if ``old`` is not present.
        """
        bucket = self._data.get(ns)
        if bucket is None or old not in bucket:
            return False
        bucket[new] = bucket.pop(old)
        self._save()
        return True

    def count(self, ns: str = DEFAULT_NS) -> int:
        return len(self._data.get(ns, {}))

    def namespaces(self) -> list[str]:
        """Sorted names of namespaces that currently contain at least one key."""
        return sorted(ns for ns, bucket in self._data.items() if bucket)

    def search(self, substring: str, ns: str = DEFAULT_NS) -> list[str]:
        """Sorted keys in ``ns`` that contain ``substring`` (case-sensitive)."""
        return sorted(k for k in self._data.get(ns, {}) if substring in k)

    # ------------------------------------------------------- import/export

    def export_json(self, path: str) -> None:
        """Write the whole store to ``path`` as ``{namespace: {key: value}}``.

        The output uses the same layout as the data file itself.
        """
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            json.dump(self._data, f, indent=2, sort_keys=True, ensure_ascii=False)
            f.write("\n")

    def import_json(self, path: str) -> None:
        """Merge a ``{namespace: {key: value}}`` file into the store.

        Keys present in the file overwrite existing values; everything else
        in the store is left untouched. The file is validated before any
        change is made, so a malformed file leaves the store unchanged.
        """
        with open(path, encoding="utf-8") as f:
            incoming = json.load(f)
        _validate(incoming)
        for ns, bucket in incoming.items():
            if bucket:
                self._data.setdefault(ns, {}).update(bucket)
        self._save()

    # ------------------------------------------------------------ lifecycle

    def close(self) -> None:
        # Every mutation is already on disk; nothing is buffered.
        pass

    def __enter__(self) -> "Store":
        return self

    def __exit__(self, *exc) -> None:
        self.close()


def _validate(data: object) -> None:
    """Raise ``ValueError`` unless ``data`` is ``{str: {str: str}}``."""
    if not isinstance(data, dict):
        raise ValueError("store data must be a JSON object of namespaces")
    for ns, bucket in data.items():
        if not isinstance(bucket, dict):
            raise ValueError(f"namespace {ns!r} must map to a JSON object")
        for key, value in bucket.items():
            if not isinstance(value, str):
                raise ValueError(
                    f"value for {ns!r}/{key!r} must be a string, not "
                    f"{type(value).__name__}"
                )
