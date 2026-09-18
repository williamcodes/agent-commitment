"""Approach A: the whole store is one JSON document {namespace: {key: value}} on disk.
Reads load the file; writes rewrite it."""
from __future__ import annotations
import json
import os


class Store:
    def __init__(self, path: str):
        self._path = path
        if not os.path.exists(path):
            self._save({})

    # ---- persistence -------------------------------------------------------------------
    def _load(self) -> dict[str, dict[str, str]]:
        with open(self._path, encoding="utf-8") as f:
            text = f.read()
        return json.loads(text) if text.strip() else {}

    def _save(self, data: dict[str, dict[str, str]]) -> None:
        # drop empty namespaces so namespaces() stays accurate
        data = {ns: kv for ns, kv in data.items() if kv}
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=True)

    # ---- T1 ----------------------------------------------------------------------------
    def set(self, key: str, value: str, ns: str = "default") -> None:
        data = self._load()
        data.setdefault(ns, {})[key] = value
        self._save(data)

    def get(self, key: str, ns: str = "default") -> str | None:
        return self._load().get(ns, {}).get(key)

    def delete(self, key: str, ns: str = "default") -> bool:
        data = self._load()
        bucket = data.get(ns, {})
        if key not in bucket:
            return False
        del bucket[key]
        self._save(data)
        return True

    def keys(self, ns: str = "default") -> list[str]:
        return sorted(self._load().get(ns, {}))

    def close(self) -> None:
        pass

    # ---- T2 ----------------------------------------------------------------------------
    def count(self, ns: str = "default") -> int:
        return len(self._load().get(ns, {}))

    def namespaces(self) -> list[str]:
        return sorted(ns for ns, kv in self._load().items() if kv)

    # ---- T3 ----------------------------------------------------------------------------
    def search(self, substring: str, ns: str = "default") -> list[str]:
        return sorted(k for k in self._load().get(ns, {}) if substring in k)

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

    # ---- T4 ----------------------------------------------------------------------------
    def rename(self, old: str, new: str, ns: str = "default") -> bool:
        data = self._load()
        bucket = data.get(ns, {})
        if old not in bucket:
            return False
        bucket[new] = bucket.pop(old)
        self._save(data)
        return True

    def items(self, ns: str = "default") -> list[tuple[str, str]]:
        return sorted(self._load().get(ns, {}).items())
