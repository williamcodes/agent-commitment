"""A tiny persistent key-value store backed by a single JSON text file.

Design: Approach A from SPEC.md. The data file at ``path`` is one JSON
object of the shape ``{namespace: {key: value}}``, pretty-printed with
sorted keys, one entry per line, UTF-8, non-ASCII left unescaped. That
makes it readable and editable by hand and produces meaningful
line-based diffs under version control. The same layout is used by
``export_json``/``import_json``, so an export is byte-for-byte a valid
data file.

Runtime model: the file is parsed once when the store is opened and held
in memory; every mutation rewrites the whole file. Stores are small
(a few thousand keys at most) and used by a single process, so this is
both simpler and faster than re-reading on every access. Rewrites go
through a temporary file in the same directory followed by an atomic
rename, so a crash mid-write can never leave a truncated or half-written
data file behind.

Files written by the earlier SQLite-backed version of this module are
detected by their header and converted to JSON on first open.
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
    """Persistent, namespaced string-to-string map in one JSON text file."""

    def __init__(self, path: str) -> None:
        self._path = path
        self._closed = False
        self._data: Data = self._load(path)
        if not os.path.exists(path):
            self._write()

    # -- persistence --------------------------------------------------------

    @classmethod
    def _load(cls, path: str) -> Data:
        if not os.path.exists(path):
            return {}
        with open(path, "rb") as fh:
            raw = fh.read()
        if not raw.strip():
            # An empty (e.g. freshly touched) file is an empty store.
            return {}
        if raw.startswith(_SQLITE_MAGIC):
            data = cls._read_legacy_sqlite(path)
            cls._atomic_write(path, data)
            return data
        try:
            obj = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"{path}: not valid JSON: {exc}") from exc
        return cls._validate(obj, path)

    @staticmethod
    def _validate(obj: object, path: str) -> Data:
        """Check the parsed document is ``{str: {str: str}}`` and copy it.

        Namespaces with no keys are dropped so hand-edited leftovers like
        ``"old": {}`` do not show up in :meth:`namespaces`.
        """
        if not isinstance(obj, dict):
            raise ValueError(f"{path}: top level must be a JSON object")
        data: Data = {}
        for ns, entries in obj.items():
            if not isinstance(entries, dict):
                raise ValueError(
                    f"{path}: namespace {ns!r} must map to a JSON object"
                )
            for key, value in entries.items():
                if not isinstance(value, str):
                    raise ValueError(
                        f"{path}: value for {ns!r}/{key!r} must be a string"
                    )
            if entries:
                data[ns] = dict(entries)
        return data

    @staticmethod
    def _read_legacy_sqlite(path: str) -> Data:
        """Extract rows from a data file written by the SQLite-backed version."""
        conn = sqlite3.connect(path)
        try:
            cols = [r[1] for r in conn.execute("PRAGMA table_info(kv)")]
            if "ns" in cols:
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

    @staticmethod
    def _dumps(data: Data) -> str:
        return json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n"

    @classmethod
    def _atomic_write(cls, path: str, data: Data) -> None:
        directory = os.path.dirname(os.path.abspath(path))
        fd, tmp = tempfile.mkstemp(prefix=".kvstore-", suffix=".tmp", dir=directory)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(cls._dumps(data))
            os.replace(tmp, path)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    def _write(self) -> None:
        self._atomic_write(self._path, self._data)

    def _check_open(self) -> None:
        if self._closed:
            raise ValueError("Store is closed")

    # -- public interface ---------------------------------------------------

    def set(self, key: str, value: str, ns: str = DEFAULT_NS) -> None:
        self._check_open()
        self._data.setdefault(ns, {})[key] = value
        self._write()

    def get(self, key: str, ns: str = DEFAULT_NS) -> str | None:
        self._check_open()
        return self._data.get(ns, {}).get(key)

    def delete(self, key: str, ns: str = DEFAULT_NS) -> bool:
        self._check_open()
        entries = self._data.get(ns)
        if entries is None or key not in entries:
            return False
        del entries[key]
        if not entries:
            del self._data[ns]
        self._write()
        return True

    def rename(self, old: str, new: str, ns: str = DEFAULT_NS) -> bool:
        """Move the value at ``old`` to ``new`` within ``ns``.

        Any existing value at ``new`` is overwritten. Returns False (and
        changes nothing) if ``old`` is not present. Renaming a key to
        itself is a no-op that returns True.
        """
        self._check_open()
        entries = self._data.get(ns)
        if entries is None or old not in entries:
            return False
        if old == new:
            return True
        entries[new] = entries.pop(old)
        self._write()
        return True

    def keys(self, ns: str = DEFAULT_NS) -> list[str]:
        self._check_open()
        return sorted(self._data.get(ns, {}))

    def items(self, ns: str = DEFAULT_NS) -> list[tuple[str, str]]:
        """All ``(key, value)`` pairs in ``ns``, sorted by key."""
        self._check_open()
        return sorted(self._data.get(ns, {}).items())

    def count(self, ns: str = DEFAULT_NS) -> int:
        self._check_open()
        return len(self._data.get(ns, {}))

    def namespaces(self) -> list[str]:
        self._check_open()
        return sorted(self._data)

    def search(self, substring: str, ns: str = DEFAULT_NS) -> list[str]:
        """Sorted keys in ``ns`` containing ``substring`` (case-sensitive)."""
        self._check_open()
        return sorted(k for k in self._data.get(ns, {}) if substring in k)

    def export_json(self, path: str) -> None:
        """Write the whole store to ``path`` as ``{namespace: {key: value}}``."""
        self._check_open()
        self._atomic_write(path, self._data)

    def import_json(self, path: str) -> None:
        """Merge a ``{namespace: {key: value}}`` file into the store.

        Existing keys are overwritten by the imported values; keys absent
        from the file are left untouched.
        """
        self._check_open()
        with open(path, "rb") as fh:
            raw = fh.read()
        try:
            obj = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"{path}: not valid JSON: {exc}") from exc
        incoming = self._validate(obj, path)
        for ns, entries in incoming.items():
            self._data.setdefault(ns, {}).update(entries)
        self._write()

    def close(self) -> None:
        # Every mutation is already written through, so nothing to flush.
        self._closed = True

    # -- conveniences -------------------------------------------------------

    def __enter__(self) -> "Store":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
