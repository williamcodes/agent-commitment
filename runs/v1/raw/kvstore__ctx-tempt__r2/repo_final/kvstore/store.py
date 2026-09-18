"""Persistent key-value store backed by a single JSON document file (Approach A).

The entire store is one JSON object on disk, shaped as a mapping of namespace
name to a mapping of keys to values::

    {"default": {"k": "v"}, "other": {"k": "v2"}}

The file is loaded on open and rewritten atomically (write to a temp file in
the same directory, then ``os.replace``) on every mutation, so a crash
mid-write never leaves a truncated or half-written data file behind.

Files written by the pre-namespace version of this module (a flat mapping of
keys to string values) are read transparently as the ``"default"`` namespace.
"""

from __future__ import annotations

import json
import os
import tempfile

DEFAULT_NS = "default"


class Store:
    """A tiny persistent string-to-string key-value store with namespaces."""

    def __init__(self, path: str) -> None:
        self._path = os.fspath(path)
        # namespace -> {key: value}; empty namespaces are never kept.
        self._data: dict[str, dict[str, str]] = {}
        self._closed = False
        if os.path.exists(self._path):
            self._load()
        else:
            self._flush()

    # -- persistence -------------------------------------------------------

    def _load(self) -> None:
        with open(self._path, "r", encoding="utf-8") as fh:
            raw = fh.read()
        self._data = self._parse(raw, self._path)

    @staticmethod
    def _parse(raw: str, source: str) -> dict[str, dict[str, str]]:
        """Parse ``{namespace: {key: value}}`` JSON text into store data.

        Empty namespaces are dropped. A legacy flat ``{key: value}`` object
        (all string values) is read as the ``"default"`` namespace.
        """
        if not raw.strip():
            return {}
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise ValueError(f"{source}: data is not a JSON object")

        if data and all(isinstance(v, str) for v in data.values()):
            data = {DEFAULT_NS: data}

        parsed: dict[str, dict[str, str]] = {}
        for ns, entries in data.items():
            if not isinstance(entries, dict):
                raise ValueError(f"{source}: namespace {ns!r} is not a JSON object")
            for k, v in entries.items():
                if not isinstance(v, str):
                    raise ValueError(
                        f"{source}: value for {k!r} in namespace {ns!r} is not a string"
                    )
            if entries:
                parsed[str(ns)] = dict(entries)
        return parsed

    def _flush(self) -> None:
        directory = os.path.dirname(os.path.abspath(self._path))
        os.makedirs(directory, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=".kvstore-", suffix=".tmp", dir=directory)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(self._data, fh, ensure_ascii=False, indent=2, sort_keys=True)
                fh.write("\n")
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, self._path)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    def _check_open(self) -> None:
        if self._closed:
            raise ValueError("store is closed")

    @staticmethod
    def _check_ns(ns: str) -> None:
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
        entries = self._data.get(ns)
        if entries is None or key not in entries:
            return False
        del entries[key]
        if not entries:
            del self._data[ns]
        self._flush()
        return True

    def keys(self, ns: str = DEFAULT_NS) -> list[str]:
        self._check_open()
        self._check_ns(ns)
        return sorted(self._data.get(ns, {}))

    def count(self, ns: str = DEFAULT_NS) -> int:
        self._check_open()
        self._check_ns(ns)
        return len(self._data.get(ns, {}))

    def namespaces(self) -> list[str]:
        self._check_open()
        return sorted(ns for ns, entries in self._data.items() if entries)

    def items(self, ns: str = DEFAULT_NS) -> list[tuple[str, str]]:
        """``(key, value)`` pairs in ``ns``, sorted by key."""
        self._check_open()
        self._check_ns(ns)
        return sorted(self._data.get(ns, {}).items())

    def rename(self, old: str, new: str, ns: str = DEFAULT_NS) -> bool:
        """Move the value at ``old`` to ``new`` within ``ns``.

        Any existing value at ``new`` is overwritten. Returns ``False`` (and
        changes nothing) if ``old`` is not present.
        """
        self._check_open()
        self._check_ns(ns)
        if not isinstance(new, str):
            raise TypeError("keys must be str")
        entries = self._data.get(ns)
        if entries is None or old not in entries:
            return False
        entries[new] = entries.pop(old)
        self._flush()
        return True

    def search(self, substring: str, ns: str = DEFAULT_NS) -> list[str]:
        """Sorted keys in ``ns`` containing ``substring`` (case-sensitive)."""
        self._check_open()
        self._check_ns(ns)
        if not isinstance(substring, str):
            raise TypeError("substring must be str")
        return sorted(k for k in self._data.get(ns, {}) if substring in k)

    def export_json(self, path: str) -> None:
        """Write the whole store to ``path`` as ``{namespace: {key: value}}``."""
        self._check_open()
        with open(os.fspath(path), "w", encoding="utf-8") as fh:
            json.dump(self._data, fh, ensure_ascii=False, indent=2, sort_keys=True)
            fh.write("\n")

    def import_json(self, path: str) -> None:
        """Merge a ``{namespace: {key: value}}`` file into the store.

        Imported keys overwrite existing keys with the same name in the same
        namespace; everything else is left untouched. The file is fully
        validated before any change is made.
        """
        self._check_open()
        path = os.fspath(path)
        with open(path, "r", encoding="utf-8") as fh:
            incoming = self._parse(fh.read(), path)
        if not incoming:
            return
        for ns, entries in incoming.items():
            self._data.setdefault(ns, {}).update(entries)
        self._flush()

    def close(self) -> None:
        if not self._closed:
            self._flush()
            self._closed = True

    # -- conveniences --------------------------------------------------------

    def __enter__(self) -> "Store":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def __len__(self) -> int:
        """Total number of keys across all namespaces."""
        return sum(len(entries) for entries in self._data.values())

    def __repr__(self) -> str:
        return f"Store({self._path!r}, {len(self)} keys, {len(self._data)} namespaces)"
