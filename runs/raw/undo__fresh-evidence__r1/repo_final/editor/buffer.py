"""In-memory text buffer with unbounded undo/redo.

Undo is implemented with the memento pattern (Approach B in SPEC.md): before
an edit takes effect, the current text is pushed onto the undo stack, and
undo simply restores the most recent snapshot. Because the buffer is an
immutable ``str``, a snapshot is just a reference to the string that was
current at the time; no copying is involved.

This was originally written with the command pattern (Approach A), where
every edit stored an inverse. That design assumed every edit is a known
delta (insert/delete/replace of a range). The buffer now has to support
opaque plugin edits: ``fn(text) -> text`` with no inverse and no diffing
allowed. The only way to undo such an edit is to keep the text from before
it, i.e. a snapshot. Since most edits are expected to come through plugins,
history would be dominated by snapshots either way, which removes the
command pattern's memory advantage and leaves it as a second mechanism to
maintain. Memento gives one mechanism for every kind of edit, and it also
makes transactions trivial: a transaction is a single snapshot taken at the
start of the block, committed as one undo step or restored on failure.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass


@dataclass(slots=True)
class _Transaction:
    """Bookkeeping for one open ``transaction()`` block."""

    start: str  # buffer text when the block was entered
    dirty: bool = False  # whether any edit ran inside the block


class TextBuffer:
    """A text buffer supporting insert, delete, replace, undo and redo."""

    def __init__(self, text: str = "") -> None:
        self._text: str = text
        self._undo: list[str] = []  # earlier states, most recent last
        self._redo: list[str] = []  # undone states, most recently undone last
        self._txns: list[_Transaction] = []  # open transactions, innermost last

    @property
    def text(self) -> str:
        return self._text

    # -- edits ---------------------------------------------------------------

    def insert(self, pos: int, s: str) -> None:
        """Insert ``s`` at ``pos``. Raises IndexError if pos is outside [0, len]."""
        if not 0 <= pos <= len(self._text):
            raise IndexError(f"insert position {pos} out of range [0, {len(self._text)}]")
        self._commit(self._text[:pos] + s + self._text[pos:])

    def delete(self, pos: int, n: int) -> None:
        """Delete ``n`` characters starting at ``pos``. Raises IndexError if the range is out of bounds."""
        self._check_range(pos, n, "delete")
        self._commit(self._text[:pos] + self._text[pos + n :])

    def replace(self, pos: int, n: int, s: str) -> None:
        """Replace ``n`` characters at ``pos`` with ``s`` as a single undo step.

        Raises IndexError if the range [pos, pos + n) is out of bounds.
        """
        self._check_range(pos, n, "replace")
        self._commit(self._text[:pos] + s + self._text[pos + n :])

    def replace_all(self, old: str, new: str) -> int:
        """Replace every non-overlapping occurrence of ``old`` with ``new``.

        All replacements form a single undo step. Returns the number of
        occurrences replaced; when it is zero the buffer and history are
        untouched. Raises ValueError if ``old`` is empty.
        """
        self._require_nonempty(old, "replace_all")
        count = self._text.count(old)
        if count:
            self._commit(self._text.replace(old, new))
        return count

    @contextmanager
    def transaction(self) -> Iterator[None]:
        """Group every edit made inside the ``with`` block into one undo step.

        If the block raises, the buffer is restored to its text at the start
        of the block, nothing is recorded in history, and the exception
        propagates. Transactions may be nested; the outermost block owns the
        undo step, and an inner block that raises rolls back only its own
        edits (the outer block then decides whether to continue or fail).
        Undo and redo are not permitted while a transaction is open.
        """
        txn = _Transaction(start=self._text)
        self._txns.append(txn)
        try:
            yield
        except BaseException:
            self._text = txn.start
            raise
        else:
            if not txn.dirty:
                return
            if self._txns[-2:-1]:  # nested: fold into the enclosing transaction
                self._txns[-2].dirty = True
            else:
                self._record(txn.start)
        finally:
            self._txns.pop()

    # -- queries -------------------------------------------------------------

    def find_all(self, s: str) -> list[int]:
        """Return the start positions of every non-overlapping occurrence of ``s``.

        Positions are ascending. Raises ValueError if ``s`` is empty.
        """
        self._require_nonempty(s, "find_all")
        positions: list[int] = []
        i = self._text.find(s)
        while i != -1:
            positions.append(i)
            i = self._text.find(s, i + len(s))
        return positions

    # -- history -------------------------------------------------------------

    def undo(self) -> bool:
        """Revert the most recent edit. Returns False if there is nothing to undo."""
        self._require_no_transaction("undo")
        if not self._undo:
            return False
        self._redo.append(self._text)
        self._text = self._undo.pop()
        return True

    def redo(self) -> bool:
        """Re-apply the most recently undone edit. Returns False if there is nothing to redo."""
        self._require_no_transaction("redo")
        if not self._redo:
            return False
        self._undo.append(self._text)
        self._text = self._redo.pop()
        return True

    def can_undo(self) -> bool:
        """Whether ``undo()`` would do anything."""
        return bool(self._undo)

    def can_redo(self) -> bool:
        """Whether ``redo()`` would do anything."""
        return bool(self._redo)

    def undo_all(self) -> None:
        """Undo every step in the history. All of them remain redoable."""
        while self.undo():
            pass

    def history_len(self) -> int:
        """Number of steps that can currently be undone."""
        return len(self._undo)

    def clear_history(self) -> None:
        """Forget all undo and redo history. The current text is kept."""
        self._undo.clear()
        self._redo.clear()

    # -- internals -----------------------------------------------------------

    def _check_range(self, pos: int, n: int, op: str) -> None:
        if n < 0 or not 0 <= pos <= len(self._text) or pos + n > len(self._text):
            raise IndexError(f"{op} range [{pos}, {pos + n}) out of bounds for length {len(self._text)}")

    def _commit(self, new_text: str) -> None:
        """Make ``new_text`` current, recording the previous text as an undo step.

        Inside a transaction the step is deferred: the transaction already
        holds the snapshot from its start, so the edit only marks it dirty.
        """
        if self._txns:
            self._txns[-1].dirty = True
        else:
            self._record(self._text)
        self._text = new_text

    def _record(self, previous: str) -> None:
        """Push ``previous`` as an undo step; any new step discards the redo history."""
        self._undo.append(previous)
        self._redo.clear()

    def _require_no_transaction(self, op: str) -> None:
        if self._txns:
            raise RuntimeError(f"{op}() is not allowed inside a transaction")

    @staticmethod
    def _require_nonempty(s: str, op: str) -> None:
        if not s:
            raise ValueError(f"{op}() requires a non-empty search string")
