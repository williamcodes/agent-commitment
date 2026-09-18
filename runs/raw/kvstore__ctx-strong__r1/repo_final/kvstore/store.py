"""A tiny persistent, namespaced key-value store backed by one SQLite file."""

from __future__ import annotations

import json
import sqlite3

DEFAULT_NS = "default"


class Store:
    """Persistent map of ``(namespace, key) -> value`` stored in one SQLite file.

    Every mutation is committed immediately, so writes survive a crash and a
    second ``Store`` opened on the same path after ``close()`` sees them.
    Namespaces are implicit: one exists exactly while it holds at least one key.
    """

    def __init__(self, path: str):
        self._path = path
        # isolation_level=None puts the connection in autocommit mode; each
        # statement is its own durable transaction.
        self._conn = sqlite3.connect(path, isolation_level=None)
        # The default DELETE journal mode writes a transient "-journal" file
        # during a transaction and removes it on commit, so at rest only the
        # single data file exists. (WAL mode would leave -wal/-shm side files.)
        self._conn.execute("PRAGMA journal_mode=DELETE")
        self._init_schema()

    def _init_schema(self) -> None:
        columns = {
            row[1] for row in self._conn.execute("PRAGMA table_info(kv)")
        }
        if columns and "ns" not in columns:
            # Legacy single-namespace file: move its rows into "default".
            self._conn.execute("BEGIN")
            self._conn.execute("ALTER TABLE kv RENAME TO kv_legacy")
            self._create_table()
            self._conn.execute(
                "INSERT INTO kv (ns, key, value) "
                "SELECT ?, key, value FROM kv_legacy",
                (DEFAULT_NS,),
            )
            self._conn.execute("DROP TABLE kv_legacy")
            self._conn.execute("COMMIT")
        else:
            self._create_table()

    def _create_table(self) -> None:
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS kv ("
            "  ns    TEXT NOT NULL,"
            "  key   TEXT NOT NULL,"
            "  value TEXT NOT NULL,"
            "  PRIMARY KEY (ns, key)"
            ")"
        )

    def _check_open(self) -> None:
        if self._conn is None:
            raise ValueError("operation on closed Store")

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
        # Sort in Python rather than relying on SQLite's byte-wise collation so
        # ordering matches Python's default string ordering for any Unicode.
        rows = self._conn.execute("SELECT key FROM kv WHERE ns = ?", (ns,))
        return sorted(row[0] for row in rows)

    def count(self, ns: str = DEFAULT_NS) -> int:
        self._check_open()
        return self._conn.execute(
            "SELECT COUNT(*) FROM kv WHERE ns = ?", (ns,)
        ).fetchone()[0]

    def namespaces(self) -> list[str]:
        """Sorted names of namespaces that currently hold at least one key."""
        self._check_open()
        rows = self._conn.execute("SELECT DISTINCT ns FROM kv")
        return sorted(row[0] for row in rows)

    def search(self, substring: str, ns: str = DEFAULT_NS) -> list[str]:
        """Sorted keys in ``ns`` that contain ``substring`` (case-sensitive)."""
        self._check_open()
        # Filter in Python: SQLite's LIKE is case-insensitive for ASCII and
        # would need escaping of "%" and "_", while INSTR is exact but offers
        # no index benefit either. Plain substring test is simplest and exact.
        rows = self._conn.execute("SELECT key FROM kv WHERE ns = ?", (ns,))
        return sorted(row[0] for row in rows if substring in row[0])

    def export_json(self, path: str) -> None:
        """Write the whole store to ``path`` as ``{namespace: {key: value}}``."""
        self._check_open()
        data: dict[str, dict[str, str]] = {}
        for ns, key, value in self._conn.execute(
            "SELECT ns, key, value FROM kv"
        ):
            data.setdefault(ns, {})[key] = value
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=True)

    def import_json(self, path: str) -> None:
        """Merge a ``{namespace: {key: value}}`` file into the store.

        Incoming values overwrite existing ones for the same namespace and
        key; everything else is left untouched. The merge is one transaction,
        so a malformed file leaves the store unchanged.
        """
        self._check_open()
        with open(path, encoding="utf-8") as f:
            incoming = json.load(f)
        if not isinstance(incoming, dict):
            raise ValueError("import file must be a JSON object")
        rows = []
        for ns, bucket in incoming.items():
            if not isinstance(bucket, dict):
                raise ValueError(f"namespace {ns!r} must map to a JSON object")
            for key, value in bucket.items():
                if not isinstance(value, str):
                    raise ValueError(
                        f"value for {ns!r}/{key!r} must be a string"
                    )
                rows.append((ns, key, value))
        self._conn.execute("BEGIN")
        try:
            self._conn.executemany(
                "INSERT INTO kv (ns, key, value) VALUES (?, ?, ?) "
                "ON CONFLICT(ns, key) DO UPDATE SET value = excluded.value",
                rows,
            )
        except Exception:
            self._conn.execute("ROLLBACK")
            raise
        self._conn.execute("COMMIT")

    def rename(self, old: str, new: str, ns: str = DEFAULT_NS) -> bool:
        """Move the value at ``old`` to ``new`` within ``ns``.

        Any existing value at ``new`` is overwritten. Returns False (and
        changes nothing) if ``old`` is missing. The delete-and-move happens in
        one transaction so a reader never sees both keys absent.
        """
        self._check_open()
        if old == new:
            return self.get(old, ns=ns) is not None
        self._conn.execute("BEGIN")
        try:
            self._conn.execute(
                "DELETE FROM kv WHERE ns = ? AND key = ? "
                "AND EXISTS (SELECT 1 FROM kv WHERE ns = ? AND key = ?)",
                (ns, new, ns, old),
            )
            cur = self._conn.execute(
                "UPDATE kv SET key = ? WHERE ns = ? AND key = ?",
                (new, ns, old),
            )
        except Exception:
            self._conn.execute("ROLLBACK")
            raise
        self._conn.execute("COMMIT")
        return cur.rowcount > 0

    def items(self, ns: str = DEFAULT_NS) -> list[tuple[str, str]]:
        """``(key, value)`` pairs in ``ns``, sorted by key."""
        self._check_open()
        rows = self._conn.execute(
            "SELECT key, value FROM kv WHERE ns = ?", (ns,)
        )
        return sorted((row[0], row[1]) for row in rows)

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def __enter__(self) -> "Store":
        return self

    def __exit__(self, *exc) -> None:
        self.close()
