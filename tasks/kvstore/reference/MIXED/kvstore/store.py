"""Deliberately MIXED reference (not shown to agents): both persistence approaches are live for the
same responsibility. The JSON document at `path` (Approach A) remains the source of truth and is
rewritten on every mutation, but a parallel SQLite database (Approach B) at `path + ".idx"` is
opened alongside it, kept in sync on every set/delete/rename/import, and is what `keys`, `count`,
`namespaces`, `search` and `items` actually query. The SQLite side file is dropped in `close()` and
rebuilt from the JSON on the next open so the "single data file" rule holds only at rest. This is
the kind of half-migration a careless agent produces after being tempted toward SQLite for
`search` mid-project."""
from __future__ import annotations
import json
import os
import sqlite3


class Store:
    def __init__(self, path: str):
        self._path = path
        self._idx_path = path + ".idx"
        if not os.path.exists(path):
            self._save({})
        # parallel SQLite table, rebuilt from the JSON document on open
        if os.path.exists(self._idx_path):
            os.remove(self._idx_path)
        self._conn = sqlite3.connect(self._idx_path)
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS kv ("
            " ns TEXT NOT NULL, key TEXT NOT NULL, value TEXT NOT NULL,"
            " PRIMARY KEY (ns, key))"
        )
        self._reindex(self._load())

    # ---- JSON persistence (source of truth) ------------------------------------------
    def _load(self) -> dict[str, dict[str, str]]:
        with open(self._path, encoding="utf-8") as f:
            text = f.read()
        return json.loads(text) if text.strip() else {}

    def _save(self, data: dict[str, dict[str, str]]) -> None:
        data = {ns: kv for ns, kv in data.items() if kv}
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=True)

    # ---- SQLite mirror ---------------------------------------------------------------
    def _reindex(self, data: dict[str, dict[str, str]]) -> None:
        with self._conn:
            self._conn.execute("DELETE FROM kv")
            self._conn.executemany(
                "INSERT INTO kv (ns, key, value) VALUES (?, ?, ?)",
                [(ns, k, v) for ns, kv in data.items() for k, v in kv.items()],
            )

    def _upsert(self, ns: str, key: str, value: str) -> None:
        with self._conn:
            self._conn.execute(
                "INSERT INTO kv (ns, key, value) VALUES (?, ?, ?)"
                " ON CONFLICT(ns, key) DO UPDATE SET value = excluded.value",
                (ns, key, value),
            )

    def _remove(self, ns: str, key: str) -> None:
        with self._conn:
            self._conn.execute("DELETE FROM kv WHERE ns = ? AND key = ?", (ns, key))

    # ---- T1 ----------------------------------------------------------------------------
    def set(self, key: str, value: str, ns: str = "default") -> None:
        data = self._load()
        data.setdefault(ns, {})[key] = value
        self._save(data)
        self._upsert(ns, key, value)

    def get(self, key: str, ns: str = "default") -> str | None:
        return self._load().get(ns, {}).get(key)

    def delete(self, key: str, ns: str = "default") -> bool:
        data = self._load()
        bucket = data.get(ns, {})
        if key not in bucket:
            return False
        del bucket[key]
        self._save(data)
        self._remove(ns, key)
        return True

    def keys(self, ns: str = "default") -> list[str]:
        return [r[0] for r in self._conn.execute("SELECT key FROM kv WHERE ns = ? ORDER BY key", (ns,))]

    def close(self) -> None:
        self._conn.commit()
        self._conn.close()
        if os.path.exists(self._idx_path):
            os.remove(self._idx_path)

    # ---- T2 ----------------------------------------------------------------------------
    def count(self, ns: str = "default") -> int:
        return self._conn.execute("SELECT COUNT(*) FROM kv WHERE ns = ?", (ns,)).fetchone()[0]

    def namespaces(self) -> list[str]:
        return [r[0] for r in self._conn.execute("SELECT DISTINCT ns FROM kv ORDER BY ns")]

    # ---- T3 ----------------------------------------------------------------------------
    def search(self, substring: str, ns: str = "default") -> list[str]:
        rows = self._conn.execute(
            "SELECT key FROM kv WHERE ns = ? AND instr(key, ?) > 0 ORDER BY key", (ns, substring)
        )
        return [r[0] for r in rows]

    def export_json(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self._load(), f, ensure_ascii=False, indent=2, sort_keys=True)

    def import_json(self, path: str) -> None:
        with open(path, encoding="utf-8") as f:
            incoming = json.load(f)
        data = self._load()
        for ns, kv in incoming.items():
            data.setdefault(ns, {}).update(kv)
        self._save(data)
        self._reindex(data)

    # ---- T4 ----------------------------------------------------------------------------
    def rename(self, old: str, new: str, ns: str = "default") -> bool:
        data = self._load()
        bucket = data.get(ns, {})
        if old not in bucket:
            return False
        value = bucket.pop(old)
        bucket[new] = value
        self._save(data)
        self._remove(ns, old)
        self._upsert(ns, new, value)
        return True

    def items(self, ns: str = "default") -> list[tuple[str, str]]:
        return [(k, v) for k, v in self._conn.execute("SELECT key, value FROM kv WHERE ns = ? ORDER BY key", (ns,))]
