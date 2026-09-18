"""Persistent key-value store backed by a single SQLite database file.

Design (Approach B from SPEC.md): one table of (namespace, key, value) rows
managed with the standard ``sqlite3`` module. Each write is its own
transaction, so a crash mid-write never leaves a half-written file, and
lookups use the primary-key index instead of loading the whole store into
memory.

The database deliberately stays in SQLite's default rollback-journal mode.
WAL mode would create ``<path>-wal`` and ``<path>-shm`` companion files,
which would violate the spec's requirement that everything live in one file.
The rollback journal (``<path>-journal``) exists only for the duration of a
transaction and is removed when the transaction commits.
"""

from __future__ import annotations

import json
import sqlite3

DEFAULT_NS = "default"


class Store:
    """A tiny persistent, namespaced string-to-string map in one SQLite file."""

    def __init__(self, path: str) -> None:
        self._path = path
        # isolation_level=None puts the connection in autocommit mode; each
        # statement below is then its own atomic transaction unless we open
        # one explicitly (as the migration does).
        self._conn = sqlite3.connect(path, isolation_level=None)
        self._init_schema()

    # -- public interface ---------------------------------------------------

    def set(self, key: str, value: str, ns: str = DEFAULT_NS) -> None:
        self._check_open()
        self._conn.execute(
            "INSERT INTO kv (ns, key, value) VALUES (?, ?, ?) "
            "ON CONFLICT(ns, key) DO UPDATE SET value = excluded.value",
            (ns, key, value),
        )

    def get(self, key: str, ns: str = DEFAULT_NS) -> str | None:
        self._check_open()
        row = self._conn.execute(
            "SELECT value FROM kv WHERE ns = ? AND key = ?", (ns, key)
        ).fetchone()
        return None if row is None else row[0]

    def delete(self, key: str, ns: str = DEFAULT_NS) -> bool:
        self._check_open()
        cur = self._conn.execute(
            "DELETE FROM kv WHERE ns = ? AND key = ?", (ns, key)
        )
        return cur.rowcount > 0

    def keys(self, ns: str = DEFAULT_NS) -> list[str]:
        self._check_open()
        # Sort in Python so the result follows str ordering exactly rather
        # than depending on SQLite's collation.
        return sorted(
            row[0]
            for row in self._conn.execute("SELECT key FROM kv WHERE ns = ?", (ns,))
        )

    def rename(self, old: str, new: str, ns: str = DEFAULT_NS) -> bool:
        """Move the value at ``old`` to ``new``, overwriting any value at ``new``.

        Returns False (and changes nothing) if ``old`` is missing. Renaming a
        key to itself is a no-op that returns True if the key exists.
        """
        self._check_open()
        conn = self._conn
        conn.execute("BEGIN")
        try:
            if old != new:
                # Clear the destination first so the primary key stays unique
                # when the row is moved. Only do it if the source exists, so
                # a failed rename never deletes the destination.
                exists = conn.execute(
                    "SELECT 1 FROM kv WHERE ns = ? AND key = ?", (ns, old)
                ).fetchone()
                if exists is None:
                    conn.execute("COMMIT")
                    return False
                conn.execute("DELETE FROM kv WHERE ns = ? AND key = ?", (ns, new))
            cur = conn.execute(
                "UPDATE kv SET key = ? WHERE ns = ? AND key = ?", (new, ns, old)
            )
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
        return cur.rowcount > 0

    def items(self, ns: str = DEFAULT_NS) -> list[tuple[str, str]]:
        """All ``(key, value)`` pairs in ``ns``, sorted by key."""
        self._check_open()
        rows = self._conn.execute(
            "SELECT key, value FROM kv WHERE ns = ?", (ns,)
        ).fetchall()
        return sorted((k, v) for k, v in rows)

    def count(self, ns: str = DEFAULT_NS) -> int:
        self._check_open()
        (n,) = self._conn.execute(
            "SELECT COUNT(*) FROM kv WHERE ns = ?", (ns,)
        ).fetchone()
        return n

    def namespaces(self) -> list[str]:
        """Sorted names of namespaces that currently hold at least one key."""
        self._check_open()
        return sorted(row[0] for row in self._conn.execute("SELECT DISTINCT ns FROM kv"))

    def search(self, substring: str, ns: str = DEFAULT_NS) -> list[str]:
        """Sorted keys in ``ns`` that contain ``substring`` (case-sensitive)."""
        self._check_open()
        # instr() is a plain case-sensitive substring test with no wildcard
        # characters to escape, unlike LIKE (which is case-insensitive for
        # ASCII by default and treats % and _ specially).
        return sorted(
            row[0]
            for row in self._conn.execute(
                "SELECT key FROM kv WHERE ns = ? AND instr(key, ?) > 0",
                (ns, substring),
            )
        )

    def export_json(self, path: str) -> None:
        """Write the whole store to ``path`` as ``{namespace: {key: value}}``."""
        self._check_open()
        data: dict[str, dict[str, str]] = {}
        for ns, key, value in self._conn.execute(
            "SELECT ns, key, value FROM kv ORDER BY ns, key"
        ):
            data.setdefault(ns, {})[key] = value
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=True)
            f.write("\n")

    def import_json(self, path: str) -> None:
        """Merge a ``{namespace: {key: value}}`` file into the store.

        Existing keys are overwritten; keys not present in the file are left
        untouched. The merge is applied atomically: either every entry in the
        file lands or none do.
        """
        self._check_open()
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError(f"{path!r}: top level must be a JSON object")
        rows: list[tuple[str, str, str]] = []
        for ns, entries in data.items():
            if not isinstance(entries, dict):
                raise ValueError(f"{path!r}: namespace {ns!r} must map to an object")
            for key, value in entries.items():
                if not isinstance(value, str):
                    raise ValueError(
                        f"{path!r}: value for {ns!r}/{key!r} must be a string"
                    )
                rows.append((ns, key, value))

        conn = self._conn
        conn.execute("BEGIN")
        try:
            conn.executemany(
                "INSERT INTO kv (ns, key, value) VALUES (?, ?, ?) "
                "ON CONFLICT(ns, key) DO UPDATE SET value = excluded.value",
                rows,
            )
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    # -- context-manager convenience -----------------------------------------

    def __enter__(self) -> "Store":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    # -- internals ------------------------------------------------------------

    def _init_schema(self) -> None:
        conn = self._conn
        columns = {row[1] for row in conn.execute("PRAGMA table_info(kv)")}
        if columns and "ns" not in columns:
            # Pre-namespace file: (key, value) only. Move its rows into the
            # default namespace inside a single transaction.
            conn.execute("BEGIN")
            try:
                conn.execute("ALTER TABLE kv RENAME TO kv_legacy")
                self._create_table(conn)
                conn.execute(
                    "INSERT INTO kv (ns, key, value) "
                    "SELECT ?, key, value FROM kv_legacy",
                    (DEFAULT_NS,),
                )
                conn.execute("DROP TABLE kv_legacy")
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise
        else:
            self._create_table(conn)

    @staticmethod
    def _create_table(conn: sqlite3.Connection) -> None:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS kv ("
            "  ns    TEXT NOT NULL,"
            "  key   TEXT NOT NULL,"
            "  value TEXT NOT NULL,"
            "  PRIMARY KEY (ns, key)"
            ") WITHOUT ROWID"
        )

    def _check_open(self) -> None:
        if self._conn is None:
            raise ValueError(f"Store at {self._path!r} is closed")
