"""Persistent key-value store backed by a single SQLite database file (Approach B).

The store is one table of ``(namespace, key, value)`` rows whose primary key is
``(namespace, key)``::

    CREATE TABLE kv (ns TEXT, key TEXT, value TEXT, PRIMARY KEY (ns, key)) WITHOUT ROWID

Why SQLite rather than a JSON document
--------------------------------------
The store is opened concurrently by many worker processes on one machine, each doing
frequent small reads and writes, and it may hold millions of keys. Those requirements
rule out a load-once / rewrite-everything JSON file:

* **No lost writes.** Every mutation is its own SQLite transaction. SQLite's file
  locking serialises writers across processes, and each connection sees the file's
  current state, so one process can never overwrite another's changes with stale data.
* **No torn reads.** Readers see either the state before a commit or the state after
  it, never a partially written file. Commits are journaled and fsynced
  (``synchronous=FULL``), so a crash mid-write rolls back rather than corrupting.
* **Fast ``get`` at scale.** Nothing is cached in memory; ``get`` is a single indexed
  lookup on the primary key, so it costs a few page reads regardless of store size.

Single-file rule
----------------
The default rollback-journal mode is used deliberately. It creates a ``<path>-journal``
file only for the duration of a write transaction and deletes it on commit, so at rest
the store is exactly one file. WAL mode would give somewhat better read/write
concurrency, but it keeps ``-wal`` and ``-shm`` files alongside the database while any
connection is open, which the spec's "one data file" rule does not allow.

Ordering
--------
``keys()``, ``search()``, ``namespaces()`` and ``export_json()`` sort with SQLite's
default BINARY collation, i.e. by UTF-8 byte order. UTF-8 byte order equals Unicode
code-point order, which is exactly what Python's ``sorted()`` produces for ``str``.

Legacy files
------------
A data file written by the earlier JSON-document implementation (either the namespaced
``{ns: {key: value}}`` layout or the older flat ``{key: value}`` layout) is detected on
open and migrated in place into a SQLite database. The migration is a one-time,
whole-file replacement and is not safe against *concurrent* first opens of the same
legacy file; migrate old files before pointing multiple workers at them.

Process model
-------------
Each ``Store`` owns one SQLite connection. Connections must not be shared across
``fork()``; open the ``Store`` inside the worker process, not before forking.
"""

from __future__ import annotations

import json
import os
import sqlite3
import tempfile
from collections.abc import Iterable, Iterator
from typing import IO

DEFAULT_NS = "default"

# How long a call waits for another process's write to finish before raising
# sqlite3.OperationalError("database is locked"). Small transactions commit in
# milliseconds, so this is far above anything expected in normal operation.
_BUSY_TIMEOUT_S = 30.0

_SQLITE_MAGIC = b"SQLite format 3\x00"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS kv (
    ns    TEXT NOT NULL,
    key   TEXT NOT NULL,
    value TEXT NOT NULL,
    PRIMARY KEY (ns, key)
) WITHOUT ROWID
"""

_UPSERT = "INSERT OR REPLACE INTO kv (ns, key, value) VALUES (?, ?, ?)"

Document = dict[str, dict[str, str]]


class Store:
    """A tiny persistent, namespaced string -> string map living in one SQLite file."""

    def __init__(self, path: str) -> None:
        self._path = path
        self._closed = False
        self._conn: sqlite3.Connection | None = None

        legacy = _read_legacy_document(path)
        if legacy is not None:
            _migrate_legacy(path, legacy)
        self._conn = _connect(path)

    # ------------------------------------------------------------ internals

    def _check_open(self) -> sqlite3.Connection:
        if self._closed or self._conn is None:
            raise ValueError("Store is closed")
        return self._conn

    @staticmethod
    def _check_ns(ns: str) -> None:
        if not isinstance(ns, str):
            raise TypeError("ns must be str")

    # --------------------------------------------------------------- public

    def set(self, key: str, value: str, ns: str = DEFAULT_NS) -> None:
        conn = self._check_open()
        self._check_ns(ns)
        if not isinstance(key, str) or not isinstance(value, str):
            raise TypeError("key and value must be str")
        # Autocommit connection: this single statement is its own durable transaction.
        conn.execute(_UPSERT, (ns, key, value))

    def get(self, key: str, ns: str = DEFAULT_NS) -> str | None:
        conn = self._check_open()
        self._check_ns(ns)
        row = conn.execute(
            "SELECT value FROM kv WHERE ns = ? AND key = ?", (ns, key)
        ).fetchone()
        return None if row is None else row[0]

    def delete(self, key: str, ns: str = DEFAULT_NS) -> bool:
        conn = self._check_open()
        self._check_ns(ns)
        cur = conn.execute("DELETE FROM kv WHERE ns = ? AND key = ?", (ns, key))
        return cur.rowcount > 0

    def keys(self, ns: str = DEFAULT_NS) -> list[str]:
        conn = self._check_open()
        self._check_ns(ns)
        rows = conn.execute("SELECT key FROM kv WHERE ns = ? ORDER BY key", (ns,))
        return [r[0] for r in rows]

    def count(self, ns: str = DEFAULT_NS) -> int:
        conn = self._check_open()
        self._check_ns(ns)
        return conn.execute("SELECT COUNT(*) FROM kv WHERE ns = ?", (ns,)).fetchone()[0]

    def items(self, ns: str = DEFAULT_NS) -> list[tuple[str, str]]:
        """All ``(key, value)`` pairs in ``ns``, sorted by key."""
        conn = self._check_open()
        self._check_ns(ns)
        rows = conn.execute(
            "SELECT key, value FROM kv WHERE ns = ? ORDER BY key", (ns,)
        )
        return [(r[0], r[1]) for r in rows]

    def rename(self, old: str, new: str, ns: str = DEFAULT_NS) -> bool:
        """Move the value stored at ``old`` to ``new`` within ``ns``.

        Any existing value at ``new`` is overwritten. Returns True if ``old``
        existed (and was moved), False otherwise, in which case nothing changes.
        Renaming a key to itself is a no-op that returns True if the key exists.

        This is one statement and therefore one transaction: ``UPDATE OR REPLACE``
        rewrites the primary key of the ``old`` row and, if that collides with an
        existing ``new`` row, deletes the loser as part of the same change. Other
        processes never observe a state where both or neither key is present.
        """
        conn = self._check_open()
        self._check_ns(ns)
        if not isinstance(old, str) or not isinstance(new, str):
            raise TypeError("old and new must be str")
        cur = conn.execute(
            "UPDATE OR REPLACE kv SET key = ? WHERE ns = ? AND key = ?", (new, ns, old)
        )
        # rowcount counts rows the UPDATE touched, not rows the REPLACE conflict
        # resolution removed, so it is 1 iff ``old`` existed.
        return cur.rowcount > 0

    def namespaces(self) -> list[str]:
        """Sorted names of namespaces that currently contain at least one key."""
        conn = self._check_open()
        # A plain SELECT DISTINCT walks every row. This recursive CTE is a "loose
        # index scan": each step seeks to the next namespace via the (ns, key)
        # primary key, so the cost scales with the number of namespaces, not keys.
        rows = conn.execute(
            """
            WITH RECURSIVE nss(ns) AS (
                SELECT MIN(ns) FROM kv
                UNION ALL
                SELECT (SELECT MIN(ns) FROM kv WHERE ns > nss.ns)
                FROM nss WHERE nss.ns IS NOT NULL
            )
            SELECT ns FROM nss WHERE ns IS NOT NULL
            """
        )
        return [r[0] for r in rows]

    def search(self, substring: str, ns: str = DEFAULT_NS) -> list[str]:
        """Sorted keys in ``ns`` that contain ``substring`` (case-sensitive)."""
        conn = self._check_open()
        self._check_ns(ns)
        if not isinstance(substring, str):
            raise TypeError("substring must be str")
        # instr() is a case-sensitive character-wise search and, like Python's
        # ``"" in s``, treats the empty substring as matching everything.
        rows = conn.execute(
            "SELECT key FROM kv WHERE ns = ? AND instr(key, ?) > 0 ORDER BY key",
            (ns, substring),
        )
        return [r[0] for r in rows]

    def export_json(self, path: str) -> None:
        """Write the whole store to ``path`` as a JSON object ``{ns: {key: value}}``.

        The rows are streamed from a single query, so the export is a consistent
        snapshot and does not require the whole store to fit in memory.
        """
        conn = self._check_open()
        rows = conn.execute("SELECT ns, key, value FROM kv ORDER BY ns, key")
        with open(path, "w", encoding="utf-8") as fh:
            _write_document(fh, rows)

    def import_json(self, path: str) -> None:
        """Merge a JSON file of the form ``{ns: {key: value}}`` into the store.

        Keys present in the file overwrite existing values; keys not in the file are
        left untouched. The whole import is one transaction, so other processes see
        either none or all of it. A flat ``{key: value}`` object (the pre-namespace
        format) is accepted and merged into the default namespace.
        """
        conn = self._check_open()
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        doc = _parse_document(data, path)
        _write_rows(conn, _iter_rows(doc))

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    # ---------------------------------------------------------- conveniences

    def __enter__(self) -> "Store":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def __repr__(self) -> str:
        state = "closed" if self._closed else "open"
        return f"Store({self._path!r}, {state})"


# ------------------------------------------------------------------ helpers


def _connect(path: str) -> sqlite3.Connection:
    # isolation_level=None puts the connection in autocommit mode: each statement is
    # its own transaction unless we issue BEGIN explicitly (see _write_rows). The
    # timeout is SQLite's busy handler, which retries while another process holds
    # the write lock.
    conn = sqlite3.connect(path, timeout=_BUSY_TIMEOUT_S, isolation_level=None)
    try:
        # FULL is the default in rollback-journal mode; set it explicitly so a
        # commit is on stable storage before set()/delete()/import_json() return.
        conn.execute("PRAGMA synchronous = FULL")
        conn.execute(_SCHEMA)
    except sqlite3.DatabaseError as exc:
        conn.close()
        raise ValueError(f"{path}: not a kvstore database ({exc})") from exc
    return conn


def _write_rows(conn: sqlite3.Connection, rows: Iterable[tuple[str, str, str]]) -> None:
    """Upsert many rows atomically. BEGIN IMMEDIATE takes the write lock up front."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        conn.executemany(_UPSERT, rows)
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    conn.execute("COMMIT")


def _iter_rows(doc: Document) -> Iterator[tuple[str, str, str]]:
    for ns, entries in doc.items():
        for key, value in entries.items():
            yield ns, key, value


def _parse_document(data: object, source: str) -> Document:
    """Validate a decoded JSON document and normalise it to ``{ns: {key: value}}``.

    Accepts the namespaced layout and the legacy flat ``{key: value}`` layout (a
    non-empty object whose values are all strings). Empty namespaces are dropped.
    """
    if not isinstance(data, dict):
        raise ValueError(f"{source}: expected a JSON object at top level")
    if not data:
        return {}
    if all(isinstance(v, str) for v in data.values()):
        return {DEFAULT_NS: dict(data)}
    doc: Document = {}
    for ns, entries in data.items():
        if not isinstance(entries, dict):
            raise ValueError(f"{source}: expected namespace {ns!r} to map to a JSON object")
        for k, v in entries.items():
            if not isinstance(v, str):
                raise ValueError(
                    f"{source}: values in namespace {ns!r} must be strings (key {k!r})"
                )
        if entries:
            doc[ns] = dict(entries)
    return doc


def _write_document(fh: IO[str], rows: Iterable[tuple[str, str, str]]) -> None:
    """Stream ``rows`` (sorted by ns, key) as a pretty-printed JSON object.

    Produces byte-for-byte what ``json.dump(doc, fh, ensure_ascii=False,
    sort_keys=True, indent=2)`` plus a trailing newline would, without building
    ``doc`` in memory.
    """

    def dumps(s: str) -> str:
        return json.dumps(s, ensure_ascii=False)

    fh.write("{")
    current_ns: str | None = None
    for ns, key, value in rows:
        if ns != current_ns:
            if current_ns is not None:
                fh.write("\n  },")
            fh.write(f"\n  {dumps(ns)}: {{")
            current_ns = ns
            first_key = True
        fh.write("" if first_key else ",")
        fh.write(f"\n    {dumps(key)}: {dumps(value)}")
        first_key = False
    if current_ns is not None:
        fh.write("\n  }\n")
    fh.write("}\n")


def _read_legacy_document(path: str) -> Document | None:
    """Return the parsed contents of a pre-SQLite JSON data file, or None.

    None means the path is missing, an empty file, or already a SQLite database;
    all of those are handled by simply opening SQLite on it.
    """
    try:
        with open(path, "rb") as fh:
            head = fh.read(len(_SQLITE_MAGIC))
    except FileNotFoundError:
        return None
    if head == _SQLITE_MAGIC or head == b"":
        return None
    with open(path, "r", encoding="utf-8") as fh:
        raw = fh.read()
    if not raw.strip():
        # The old implementation treated a whitespace-only file as an empty store,
        # but SQLite would reject it; migrate it to an empty database.
        return {}
    try:
        data = json.loads(raw)
    except ValueError as exc:
        raise ValueError(
            f"{path}: not a kvstore database and not a legacy JSON store ({exc})"
        ) from exc
    return _parse_document(data, path)


def _migrate_legacy(path: str, doc: Document) -> None:
    """Replace the legacy JSON file at ``path`` with an equivalent SQLite database.

    The new database is built in a temporary file in the same directory and then
    atomically renamed over the original, so a crash mid-migration leaves the
    legacy file intact.
    """
    directory = os.path.dirname(os.path.abspath(path)) or "."
    fd, tmp = tempfile.mkstemp(prefix=".kvstore-migrate-", dir=directory)
    os.close(fd)
    try:
        conn = _connect(tmp)
        try:
            _write_rows(conn, _iter_rows(doc))
        finally:
            conn.close()
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
