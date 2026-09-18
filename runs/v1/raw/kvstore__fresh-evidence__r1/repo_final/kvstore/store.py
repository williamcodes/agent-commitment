"""Persistent key-value store backed by a single human-readable JSON file.

This is "Approach A" from SPEC.md. The data file is one JSON object of the
form ``{namespace: {key: value}}``, written with two-space indentation,
sorted keys, and unescaped Unicode::

    {
      "default": {
        "greeting": "héllo ✓"
      },
      "prod": {
        "db_host": "db.internal"
      }
    }

The layout is deterministic (sorted at every level, one entry per line),
so a change to one key shows up in ``git diff`` as a change to one line,
and the file can be opened and edited in any text editor.

The whole store is held in memory and rewritten on every mutation. That is
the right trade-off for this tool: stores are small (under 2,000 keys) and
only ever used by one process at a time. Writes go to a temporary file in
the same directory which is then atomically renamed over the data file, so
a crash mid-write leaves the previous contents intact rather than a
truncated file. The temporary file exists only for the duration of the
write; nothing but ``path`` is left on disk.

Keys are partitioned into *namespaces*. The same key may hold different
values in different namespaces. Every public method takes ``ns`` and
defaults it to ``"default"``, so callers that never mention namespaces see
a plain flat mapping. A namespace that becomes empty is dropped from the
file.

Data files written by the earlier SQLite backend are recognised on open and
converted to the JSON format in place (see ``_load``).
"""

from __future__ import annotations

import json
import os
import sqlite3
import tempfile

DEFAULT_NS = "default"

_SQLITE_MAGIC = b"SQLite format 3\x00"

# type alias for the in-memory / on-disk shape
_Data = dict[str, dict[str, str]]


def _validate(data: object, source: str) -> _Data:
    """Check that ``data`` has the shape ``{str: {str: str}}``.

    Raises ``ValueError`` naming ``source`` so a bad hand edit or a
    malformed import file is reported clearly instead of corrupting the
    store later.
    """
    if not isinstance(data, dict):
        raise ValueError(f"{source}: top level must be a JSON object")
    for ns, entries in data.items():
        if not isinstance(entries, dict):
            raise ValueError(
                f"{source}: namespace {ns!r} must map keys to string values"
            )
        for key, value in entries.items():
            if not isinstance(value, str):
                raise ValueError(
                    f"{source}: value for key {key!r} in namespace {ns!r} "
                    f"must be a string, not {type(value).__name__}"
                )
    return data


def _dumps(data: _Data) -> str:
    return json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def _write_atomic(path: str, text: str) -> None:
    """Write ``text`` to ``path`` via a temporary file and ``os.replace``."""
    directory = os.path.dirname(os.path.abspath(path))
    fd, tmp = tempfile.mkstemp(prefix=".", suffix=".tmp", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


class Store:
    """A tiny persistent mapping from ``str`` keys to ``str`` values."""

    def __init__(self, path: str):
        self._path = path
        self._data: _Data | None = self._load()

    # -- persistence -------------------------------------------------------

    def _load(self) -> _Data:
        """Read the data file, creating it if missing.

        An empty file is treated as an empty store, so a user may ``touch``
        the file before first use. A file left by the old SQLite backend is
        read through ``sqlite3`` and immediately rewritten as JSON.
        """
        try:
            with open(self._path, "rb") as fh:
                raw = fh.read()
        except FileNotFoundError:
            data: _Data = {}
            _write_atomic(self._path, _dumps(data))
            return data

        if raw.startswith(_SQLITE_MAGIC):
            data = self._read_sqlite()
            _write_atomic(self._path, _dumps(data))
            return data

        text = raw.decode("utf-8")
        if not text.strip():
            return {}
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as e:
            raise ValueError(f"{self._path}: not valid JSON ({e})") from e
        return _validate(parsed, self._path)

    def _read_sqlite(self) -> _Data:
        """Pull all rows out of a legacy SQLite data file.

        Handles both the namespaced table ``kv(ns, key, value)`` and the
        original flat table ``kv(key, value)``, whose rows land in the
        default namespace.
        """
        data: _Data = {}
        conn = sqlite3.connect(self._path)
        try:
            cols = [r[1] for r in conn.execute("PRAGMA table_info(kv)")]
            if not cols:
                return data
            if "ns" in cols:
                rows = conn.execute("SELECT ns, key, value FROM kv")
            else:
                rows = (
                    (DEFAULT_NS, k, v)
                    for k, v in conn.execute("SELECT key, value FROM kv")
                )
            for ns, key, value in rows:
                data.setdefault(ns, {})[key] = value
        finally:
            conn.close()
        return data

    def _save(self) -> None:
        _write_atomic(self._path, _dumps(self._store()))

    def _store(self) -> _Data:
        if self._data is None:
            raise ValueError("Store is closed")
        return self._data

    # -- public interface (see SPEC.md) ------------------------------------

    def set(self, key: str, value: str, ns: str = DEFAULT_NS) -> None:
        self._store().setdefault(ns, {})[key] = value
        self._save()

    def get(self, key: str, ns: str = DEFAULT_NS) -> str | None:
        return self._store().get(ns, {}).get(key)

    def delete(self, key: str, ns: str = DEFAULT_NS) -> bool:
        data = self._store()
        entries = data.get(ns)
        if entries is None or key not in entries:
            return False
        del entries[key]
        if not entries:
            del data[ns]
        self._save()
        return True

    def keys(self, ns: str = DEFAULT_NS) -> list[str]:
        return sorted(self._store().get(ns, {}))

    def items(self, ns: str = DEFAULT_NS) -> list[tuple[str, str]]:
        """``(key, value)`` pairs in ``ns``, sorted by key."""
        return sorted(self._store().get(ns, {}).items())

    def rename(self, old: str, new: str, ns: str = DEFAULT_NS) -> bool:
        """Move the value at ``old`` to ``new`` within ``ns``.

        Any existing value at ``new`` is overwritten. Returns ``False`` and
        changes nothing if ``old`` is missing. Renaming a key to itself is
        a no-op that returns ``True``.
        """
        entries = self._store().get(ns)
        if entries is None or old not in entries:
            return False
        if old == new:
            return True
        entries[new] = entries.pop(old)
        self._save()
        return True

    def count(self, ns: str = DEFAULT_NS) -> int:
        return len(self._store().get(ns, {}))

    def namespaces(self) -> list[str]:
        """Sorted names of namespaces that currently hold at least one key."""
        return sorted(ns for ns, entries in self._store().items() if entries)

    def search(self, substring: str, ns: str = DEFAULT_NS) -> list[str]:
        """Sorted keys in ``ns`` that contain ``substring`` (case-sensitive)."""
        return [k for k in self.keys(ns) if substring in k]

    def export_json(self, path: str) -> None:
        """Write the whole store to ``path`` as ``{namespace: {key: value}}``.

        The output uses the same layout as the data file itself.
        """
        _write_atomic(path, _dumps(self._store()))

    def import_json(self, path: str) -> None:
        """Merge a ``{namespace: {key: value}}`` file into the store.

        Existing keys are overwritten by the imported values; keys not
        present in the file are left alone. The file is validated in full
        before anything is changed, so a malformed file imports nothing.
        """
        with open(path, encoding="utf-8") as fh:
            incoming = _validate(json.load(fh), path)
        data = self._store()
        for ns, entries in incoming.items():
            if entries:
                data.setdefault(ns, {}).update(entries)
        self._save()

    def close(self) -> None:
        # Every mutation is already on disk; closing just makes further use
        # an error, matching the previous backend's behaviour.
        self._data = None

    # -- conveniences ------------------------------------------------------

    def __enter__(self) -> "Store":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def __repr__(self) -> str:
        state = "closed" if self._data is None else "open"
        return f"Store({self._path!r}, {state})"
