"""Persistent key-value store backed by a single SQLite database file.

Approach B from SPEC.md: one table of (namespace, key, value) rows managed
with the standard-library ``sqlite3`` module. Every write is committed
immediately so a second ``Store`` opened after ``close()`` sees all earlier
writes.

Namespaces are independent key spaces inside the same file. Every method that
takes a key accepts ``ns`` (default ``"default"``); the same key may hold
different values in different namespaces.

``export_json``/``import_json`` exchange the whole store with a plain JSON
document of the form ``{namespace: {key: value}}``; the SQLite file remains
the only persistent storage.
"""

from __future__ import annotations

import json
import sqlite3

DEFAULT_NS = "default"


class Store:
    """A tiny persistent key-value store living in one SQLite file at ``path``."""

    def __init__(self, path: str) -> None:
        self._path = path
        # The default rollback-journal mode keeps the temporary ``-journal`` file
        # only for the duration of a transaction, so after close() the data file
        # is the sole artifact on disk (WAL mode would leave ``-wal``/``-shm``).
        self._conn = sqlite3.connect(path)
        self._init_schema()

    def _init_schema(self) -> None:
        conn = self._conn
        with conn:
            columns = {
                row[1] for row in conn.execute("PRAGMA table_info(kv)")
            }
            if columns and "ns" not in columns:
                # Data file written by the pre-namespace version: a ``kv``
                # table keyed on ``key`` alone. Move its rows into the default
                # namespace so old data stays reachable via ``ns="default"``.
                conn.execute("ALTER TABLE kv RENAME TO kv_legacy")
                self._create_table(conn)
                conn.execute(
                    "INSERT INTO kv (ns, key, value) "
                    "SELECT ?, key, value FROM kv_legacy",
                    (DEFAULT_NS,),
                )
                conn.execute("DROP TABLE kv_legacy")
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
            ")"
        )

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
            cur = conn.execute(
                "DELETE FROM kv WHERE ns = ? AND key = ?", (ns, key)
            )
        return cur.rowcount > 0

    def keys(self, ns: str = DEFAULT_NS) -> list[str]:
        conn = self._require_open()
        # Sort in Python so ordering follows Unicode code points regardless of
        # the database's collation.
        return sorted(
            row[0] for row in conn.execute("SELECT key FROM kv WHERE ns = ?", (ns,))
        )

    def items(self, ns: str = DEFAULT_NS) -> list[tuple[str, str]]:
        """``(key, value)`` pairs in ``ns``, sorted by key (code-point order)."""
        conn = self._require_open()
        return sorted(
            (row[0], row[1])
            for row in conn.execute(
                "SELECT key, value FROM kv WHERE ns = ?", (ns,)
            )
        )

    def rename(self, old: str, new: str, ns: str = DEFAULT_NS) -> bool:
        """Move the value at ``old`` to ``new`` within ``ns``.

        Any existing value at ``new`` is overwritten. Returns ``False`` (and
        changes nothing) if ``old`` is missing. Renaming a key to itself is a
        no-op that returns ``True`` when the key exists. The whole rename is
        one transaction, so a crash cannot leave both or neither key present.
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
            # Clear the destination first: the (ns, key) primary key would
            # otherwise reject the UPDATE when ``new`` already holds a value.
            conn.execute("DELETE FROM kv WHERE ns = ? AND key = ?", (ns, new))
            conn.execute(
                "UPDATE kv SET key = ? WHERE ns = ? AND key = ?", (new, ns, old)
            )
        return True

    def count(self, ns: str = DEFAULT_NS) -> int:
        conn = self._require_open()
        return conn.execute(
            "SELECT COUNT(*) FROM kv WHERE ns = ?", (ns,)
        ).fetchone()[0]

    def namespaces(self) -> list[str]:
        """Sorted names of namespaces that currently hold at least one key."""
        conn = self._require_open()
        return sorted(row[0] for row in conn.execute("SELECT DISTINCT ns FROM kv"))

    def search(self, substring: str, ns: str = DEFAULT_NS) -> list[str]:
        """Sorted keys in ``ns`` that contain ``substring`` (case-sensitive).

        Uses ``instr`` rather than ``LIKE`` because ``LIKE`` is
        case-insensitive for ASCII and would need ``%``/``_`` escaping.
        """
        conn = self._require_open()
        return sorted(
            row[0]
            for row in conn.execute(
                "SELECT key FROM kv WHERE ns = ? AND instr(key, ?) > 0",
                (ns, substring),
            )
        )

    def export_json(self, path: str) -> None:
        """Write every namespace to ``path`` as ``{namespace: {key: value}}``."""
        conn = self._require_open()
        data: dict[str, dict[str, str]] = {}
        for ns, key, value in conn.execute("SELECT ns, key, value FROM kv"):
            data.setdefault(ns, {})[key] = value
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=True)
            f.write("\n")

    def import_json(self, path: str) -> None:
        """Merge a ``{namespace: {key: value}}`` file into the store.

        Existing keys are overwritten by the file's values; keys absent from
        the file are left untouched. The whole import is one transaction, so a
        malformed file leaves the store unchanged.
        """
        conn = self._require_open()
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError("import_json: top level must be a JSON object")
        rows: list[tuple[str, str, str]] = []
        for ns, entries in data.items():
            if not isinstance(entries, dict):
                raise ValueError(
                    f"import_json: namespace {ns!r} must map to a JSON object"
                )
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
            self._conn.commit()
            self._conn.close()
            self._conn = None

    def __enter__(self) -> "Store":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def __repr__(self) -> str:
        state = "closed" if self._conn is None else "open"
        return f"Store({self._path!r}, {state})"
