"""A tiny persistent key-value store backed by a single JSON document file.

Design (Approach A from SPEC.md): the whole store is one JSON object on disk.
The object is loaded once when the store is opened and kept in memory; every
mutating operation rewrites the file in place so the on-disk copy is always
current. Reads are served from memory.

On-disk layout (format version 2)::

    {"version": 2, "namespaces": {"default": {"k": "v"}, "other": {...}}}

Namespaces that become empty are dropped from the document, so the set of
namespace names on disk is exactly the set that contains at least one key.
A legacy flat document (``{"k": "v", ...}``) is read as the ``default``
namespace and rewritten in the new layout on the next write.
"""

from __future__ import annotations

import json
import os

DEFAULT_NS = "default"
_FORMAT_VERSION = 2


class Store:
    """Persistent mapping of (namespace, key) -> value stored as JSON at ``path``."""

    def __init__(self, path: str):
        self._path = path
        self._closed = False
        self._data: dict[str, dict[str, str]] = self._load()

    # -- persistence -------------------------------------------------------

    @staticmethod
    def _is_str_map(obj: object) -> bool:
        return isinstance(obj, dict) and all(
            isinstance(k, str) and isinstance(v, str) for k, v in obj.items()
        )

    def _load(self) -> dict[str, dict[str, str]]:
        """Read the JSON document at ``path``; create an empty one if missing."""
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                raw = f.read()
        except FileNotFoundError:
            self._data = {}
            self._flush()
            return {}

        if not raw.strip():
            # Empty file (e.g. created by ``touch``): treat as an empty store.
            return {}

        doc = json.loads(raw)
        bad = ValueError(f"{self._path}: not a kvstore JSON document")
        if not isinstance(doc, dict):
            raise bad

        if doc.get("version") == _FORMAT_VERSION and "namespaces" in doc:
            namespaces = doc["namespaces"]
            if not isinstance(namespaces, dict) or not all(
                isinstance(ns, str) and self._is_str_map(m)
                for ns, m in namespaces.items()
            ):
                raise bad
            # Drop empty namespaces so ``namespaces()`` stays accurate.
            return {ns: dict(m) for ns, m in namespaces.items() if m}

        # Legacy version-1 layout: a flat str -> str object.
        if self._is_str_map(doc):
            return {DEFAULT_NS: dict(doc)} if doc else {}
        raise bad

    def _flush(self) -> None:
        """Rewrite the data file in place with the current in-memory contents.

        The file is written directly (no temp file) so that nothing but ``path``
        ever appears on disk, per the single-file constraint in SPEC.md.
        """
        doc = {"version": _FORMAT_VERSION, "namespaces": self._data}
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False, sort_keys=True, indent=2)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())

    def _check_open(self) -> None:
        if self._closed:
            raise ValueError("operation on closed Store")

    @staticmethod
    def _check_ns(ns: object) -> None:
        if not isinstance(ns, str):
            raise TypeError("namespace must be str")

    # -- public interface --------------------------------------------------

    def set(self, key: str, value: str, ns: str = DEFAULT_NS) -> None:
        self._check_open()
        self._check_ns(ns)
        if not isinstance(key, str) or not isinstance(value, str):
            raise TypeError("keys and values must be str")
        self._data.setdefault(ns, {})[key] = value
        self._flush()

    def get(self, key: str, ns: str = DEFAULT_NS) -> str | None:
        self._check_open()
        self._check_ns(ns)
        return self._data.get(ns, {}).get(key)

    def delete(self, key: str, ns: str = DEFAULT_NS) -> bool:
        self._check_open()
        self._check_ns(ns)
        bucket = self._data.get(ns)
        if bucket is None or key not in bucket:
            return False
        del bucket[key]
        if not bucket:
            del self._data[ns]
        self._flush()
        return True

    def keys(self, ns: str = DEFAULT_NS) -> list[str]:
        self._check_open()
        self._check_ns(ns)
        return sorted(self._data.get(ns, {}))

    def count(self, ns: str = DEFAULT_NS) -> int:
        """Number of keys currently stored in ``ns``."""
        self._check_open()
        self._check_ns(ns)
        return len(self._data.get(ns, {}))

    def namespaces(self) -> list[str]:
        """Sorted names of namespaces that contain at least one key."""
        self._check_open()
        return sorted(self._data)

    def search(self, substring: str, ns: str = DEFAULT_NS) -> list[str]:
        """Sorted keys in ``ns`` that contain ``substring`` (case-sensitive)."""
        self._check_open()
        self._check_ns(ns)
        if not isinstance(substring, str):
            raise TypeError("substring must be str")
        return sorted(k for k in self._data.get(ns, {}) if substring in k)

    def rename(self, old: str, new: str, ns: str = DEFAULT_NS) -> bool:
        """Move the value at ``old`` to ``new`` within ``ns``.

        Any existing value at ``new`` is overwritten. Returns False (and
        changes nothing) if ``old`` is missing. Renaming a key to itself is a
        no-op that returns True.
        """
        self._check_open()
        self._check_ns(ns)
        if not isinstance(old, str) or not isinstance(new, str):
            raise TypeError("keys must be str")
        bucket = self._data.get(ns)
        if bucket is None or old not in bucket:
            return False
        if old != new:
            bucket[new] = bucket.pop(old)
            self._flush()
        return True

    def items(self, ns: str = DEFAULT_NS) -> list[tuple[str, str]]:
        """``(key, value)`` pairs in ``ns``, sorted by key."""
        self._check_open()
        self._check_ns(ns)
        return sorted(self._data.get(ns, {}).items())

    # -- JSON export / import ---------------------------------------------

    def export_json(self, path: str) -> None:
        """Write the whole store to ``path`` as ``{namespace: {key: value}}``."""
        self._check_open()
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, sort_keys=True, indent=2)
            f.write("\n")

    def import_json(self, path: str) -> None:
        """Merge a ``{namespace: {key: value}}`` file at ``path`` into the store.

        Existing keys are overwritten by values from the file; keys not in the
        file are left untouched. The file is validated in full before anything
        is changed, so a malformed file leaves the store as it was.
        """
        self._check_open()
        with open(path, "r", encoding="utf-8") as f:
            doc = json.load(f)
        if not isinstance(doc, dict) or not all(
            isinstance(ns, str) and self._is_str_map(m) for ns, m in doc.items()
        ):
            raise ValueError(f"{path}: not a {{namespace: {{key: value}}}} document")
        changed = False
        for ns, m in doc.items():
            if m:
                self._data.setdefault(ns, {}).update(m)
                changed = True
        if changed:
            self._flush()

    def close(self) -> None:
        """Mark the store closed. All writes are already on disk."""
        self._closed = True

    # -- conveniences ------------------------------------------------------

    def __enter__(self) -> "Store":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def __len__(self) -> int:
        """Total number of keys across all namespaces."""
        return sum(len(m) for m in self._data.values())

    def __contains__(self, key: object) -> bool:
        """True if ``key`` exists in the default namespace."""
        return key in self._data.get(DEFAULT_NS, {})

    def __repr__(self) -> str:
        state = "closed" if self._closed else "open"
        return (
            f"Store({self._path!r}, {state}, {len(self)} keys "
            f"in {len(self._data)} namespaces)"
        )
