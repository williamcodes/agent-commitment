"""Persistent key-value store backed by a single SQLite database file (Approach B)."""

from __future__ import annotations

import json
import sqlite3

DEFAULT_NS = "default"


class Store:
    """A tiny persistent, namespaced key-value store.

    All data lives in one SQLite file at ``path``. Each write is committed
    immediately, so a second ``Store`` opened on the same path after
    ``close()`` sees every earlier write.

    Keys are scoped by a namespace (``ns``); the same key may hold different
    values in different namespaces. Every method defaults to ``"default"``.
    """

    def __init__(self, path: str):
        self._path = path
        self._conn = sqlite3.connect(path)
        # Default rollback-journal mode: the journal is only ever a transient
        # file during a write and is removed on commit, so no side files
        # remain on disk (WAL mode would leave -wal/-shm files).
        self._conn.execute("PRAGMA journal_mode=DELETE")
        with self._conn:
            self._migrate_legacy_schema()
            self._conn.execute(
                "CREATE TABLE IF NOT EXISTS kv ("
                "ns TEXT NOT NULL, "
                "key TEXT NOT NULL, "
                "value TEXT NOT NULL, "
                "PRIMARY KEY (ns, key))"
            )

    def _migrate_legacy_schema(self) -> None:
        """Upgrade a pre-namespace ``kv(key, value)`` table in place.

        Existing rows are moved into the ``"default"`` namespace. No-op for
        new files or files already using the namespaced schema.
        """
        cols = [row[1] for row in self._conn.execute("PRAGMA table_info(kv)")]
        if not cols or "ns" in cols:
            return
        self._conn.execute("ALTER TABLE kv RENAME TO kv_legacy")
        self._conn.execute(
            "CREATE TABLE kv ("
            "ns TEXT NOT NULL, "
            "key TEXT NOT NULL, "
            "value TEXT NOT NULL, "
            "PRIMARY KEY (ns, key))"
        )
        self._conn.execute(
            "INSERT INTO kv (ns, key, value) SELECT ?, key, value FROM kv_legacy",
            (DEFAULT_NS,),
        )
        self._conn.execute("DROP TABLE kv_legacy")

    def _require_open(self) -> sqlite3.Connection:
        if self._conn is None:
            raise ValueError("Store is closed")
        return self._conn

    def set(self, key: str, value: str, ns: str = DEFAULT_NS) -> None:
        conn = self._require_open()
        with conn:
            conn.execute(
                "INSERT INTO kv (ns, key, value) VALUES (?, ?, ?) "
                "ON CONFLICT(ns, key) DO UPDATE SET value = excluded.value",
                (ns, key, value),
            )

    def get(self, key: str, ns: str = DEFAULT_NS) -> str | None:
        conn = self._require_open()
        row = conn.execute(
            "SELECT value FROM kv WHERE ns = ? AND key = ?", (ns, key)
        ).fetchone()
        return None if row is None else row[0]

    def delete(self, key: str, ns: str = DEFAULT_NS) -> bool:
        conn = self._require_open()
        with conn:
            cur = conn.execute("DELETE FROM kv WHERE ns = ? AND key = ?", (ns, key))
        return cur.rowcount > 0

    def keys(self, ns: str = DEFAULT_NS) -> list[str]:
        conn = self._require_open()
        return [
            row[0]
            for row in conn.execute(
                "SELECT key FROM kv WHERE ns = ? ORDER BY key", (ns,)
            )
        ]

    def count(self, ns: str = DEFAULT_NS) -> int:
        conn = self._require_open()
        return conn.execute("SELECT COUNT(*) FROM kv WHERE ns = ?", (ns,)).fetchone()[0]

    def namespaces(self) -> list[str]:
        """Sorted names of namespaces that currently contain at least one key."""
        conn = self._require_open()
        return [row[0] for row in conn.execute("SELECT DISTINCT ns FROM kv ORDER BY ns")]

    def search(self, substring: str, ns: str = DEFAULT_NS) -> list[str]:
        """Sorted keys in ``ns`` whose name contains ``substring`` (case-sensitive).

        Uses ``instr`` rather than ``LIKE``: ``LIKE`` is case-insensitive for
        ASCII and would need wildcard escaping. An empty substring matches
        every key, mirroring Python's ``"" in s``.
        """
        conn = self._require_open()
        return [
            row[0]
            for row in conn.execute(
                "SELECT key FROM kv WHERE ns = ? AND instr(key, ?) > 0 ORDER BY key",
                (ns, substring),
            )
        ]

    def rename(self, old: str, new: str, ns: str = DEFAULT_NS) -> bool:
        """Move the value at ``old`` to ``new`` within ``ns``.

        Any existing value at ``new`` is overwritten. Returns ``False`` (and
        changes nothing) if ``old`` is missing. Renaming a key to itself is a
        no-op that returns ``True`` when the key exists. The whole operation
        runs in one transaction so a crash cannot leave both or neither key.
        """
        conn = self._require_open()
        with conn:
            exists = conn.execute(
                "SELECT 1 FROM kv WHERE ns = ? AND key = ?", (ns, old)
            ).fetchone()
            if exists is None:
                return False
            if old == new:
                return True
            conn.execute("DELETE FROM kv WHERE ns = ? AND key = ?", (ns, new))
            conn.execute(
                "UPDATE kv SET key = ? WHERE ns = ? AND key = ?", (new, ns, old)
            )
        return True

    def items(self, ns: str = DEFAULT_NS) -> list[tuple[str, str]]:
        """All ``(key, value)`` pairs in ``ns``, sorted by key."""
        conn = self._require_open()
        return [
            (row[0], row[1])
            for row in conn.execute(
                "SELECT key, value FROM kv WHERE ns = ? ORDER BY key", (ns,)
            )
        ]

    def export_json(self, path: str) -> None:
        """Write the whole store to ``path`` as ``{namespace: {key: value}}``."""
        conn = self._require_open()
        data: dict[str, dict[str, str]] = {}
        for ns, key, value in conn.execute(
            "SELECT ns, key, value FROM kv ORDER BY ns, key"
        ):
            data.setdefault(ns, {})[key] = value
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write("\n")

    def import_json(self, path: str) -> None:
        """Merge a ``{namespace: {key: value}}`` JSON file into the store.

        Keys already present are overwritten by the file's values; keys not
        mentioned in the file are left untouched. The file is validated
        before any write, and the merge is applied in a single transaction.
        """
        conn = self._require_open()
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError("import_json: top level must be a JSON object")
        rows: list[tuple[str, str, str]] = []
        for ns, entries in data.items():
            if not isinstance(entries, dict):
                raise ValueError(f"import_json: namespace {ns!r} must map to an object")
            for key, value in entries.items():
                if not isinstance(value, str):
                    raise ValueError(
                        f"import_json: value for {ns!r}/{key!r} must be a string"
                    )
                rows.append((ns, key, value))
        with conn:
            conn.executemany(
                "INSERT INTO kv (ns, key, value) VALUES (?, ?, ?) "
                "ON CONFLICT(ns, key) DO UPDATE SET value = excluded.value",
                rows,
            )

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def __enter__(self) -> "Store":
        return self

    def __exit__(self, *exc) -> None:
        self.close()
