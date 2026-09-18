"""Approach B: a SQLite database file with one table of (ns, key, value) rows."""
from __future__ import annotations
import json
import sqlite3


class Store:
    def __init__(self, path: str):
        self._conn = sqlite3.connect(path)
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS kv ("
            " ns TEXT NOT NULL, key TEXT NOT NULL, value TEXT NOT NULL,"
            " PRIMARY KEY (ns, key))"
        )
        self._conn.commit()

    # ---- T1 ----------------------------------------------------------------------------
    def set(self, key: str, value: str, ns: str = "default") -> None:
        with self._conn:
            self._conn.execute(
                "INSERT INTO kv (ns, key, value) VALUES (?, ?, ?)"
                " ON CONFLICT(ns, key) DO UPDATE SET value = excluded.value",
                (ns, key, value),
            )

    def get(self, key: str, ns: str = "default") -> str | None:
        row = self._conn.execute("SELECT value FROM kv WHERE ns = ? AND key = ?", (ns, key)).fetchone()
        return None if row is None else row[0]

    def delete(self, key: str, ns: str = "default") -> bool:
        with self._conn:
            cur = self._conn.execute("DELETE FROM kv WHERE ns = ? AND key = ?", (ns, key))
        return cur.rowcount > 0

    def keys(self, ns: str = "default") -> list[str]:
        return [r[0] for r in self._conn.execute("SELECT key FROM kv WHERE ns = ? ORDER BY key", (ns,))]

    def close(self) -> None:
        self._conn.commit()
        self._conn.close()

    # ---- T2 ----------------------------------------------------------------------------
    def count(self, ns: str = "default") -> int:
        return self._conn.execute("SELECT COUNT(*) FROM kv WHERE ns = ?", (ns,)).fetchone()[0]

    def namespaces(self) -> list[str]:
        return [r[0] for r in self._conn.execute("SELECT DISTINCT ns FROM kv ORDER BY ns")]

    # ---- T3 ----------------------------------------------------------------------------
    def search(self, substring: str, ns: str = "default") -> list[str]:
        # instr() is case-sensitive, unlike LIKE
        rows = self._conn.execute(
            "SELECT key FROM kv WHERE ns = ? AND instr(key, ?) > 0 ORDER BY key", (ns, substring)
        )
        return [r[0] for r in rows]

    def export_json(self, path: str) -> None:
        data: dict[str, dict[str, str]] = {}
        for ns, key, value in self._conn.execute("SELECT ns, key, value FROM kv ORDER BY ns, key"):
            data.setdefault(ns, {})[key] = value
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def import_json(self, path: str) -> None:
        with open(path, encoding="utf-8") as f:
            incoming = json.load(f)
        with self._conn:
            self._conn.executemany(
                "INSERT INTO kv (ns, key, value) VALUES (?, ?, ?)"
                " ON CONFLICT(ns, key) DO UPDATE SET value = excluded.value",
                [(ns, k, v) for ns, kv in incoming.items() for k, v in kv.items()],
            )

    # ---- T4 ----------------------------------------------------------------------------
    def rename(self, old: str, new: str, ns: str = "default") -> bool:
        with self._conn:
            row = self._conn.execute("SELECT value FROM kv WHERE ns = ? AND key = ?", (ns, old)).fetchone()
            if row is None:
                return False
            self._conn.execute("DELETE FROM kv WHERE ns = ? AND key IN (?, ?)", (ns, old, new))
            self._conn.execute("INSERT INTO kv (ns, key, value) VALUES (?, ?, ?)", (ns, new, row[0]))
        return True

    def items(self, ns: str = "default") -> list[tuple[str, str]]:
        return [(k, v) for k, v in self._conn.execute("SELECT key, value FROM kv WHERE ns = ? ORDER BY key", (ns,))]
