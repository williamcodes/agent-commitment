"""In-memory text buffer with unbounded undo/redo.

Undo is implemented with the memento pattern (SPEC.md "Approach B"): every
undo step is a snapshot of the whole buffer text taken before the step was
applied. Undo restores the previous snapshot and parks the current text on
the redo stack; redo does the reverse.

The project originally used the command pattern (Approach A), where each
edit stored enough to compute its own inverse. That was abandoned because
the buffer must support plugin edits: opaque ``fn(text) -> text`` callables
with no inverse and for which diffing is not permitted. A snapshot is the
only thing that can undo such an edit, and since most edits are expected
to arrive through plugins, keeping a second inverse-based mechanism for
insert/delete/replace would buy little memory and cost a special case.
With snapshots, every kind of edit, including a whole transaction, goes
through the single ``_commit`` path below.

Python strings are immutable, so a snapshot is a reference, not a copy; the
cost of a step is the one new string the edit itself produces. Memory is
still proportional to buffer size times history length in the worst case,
which the spec accepts.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager


class TextBuffer:
    """A string buffer supporting insert, delete, replace, undo and redo."""

    def __init__(self, text: str = "") -> None:
        self._text = str(text)
        self._undo: list[str] = []  # snapshots taken before each recorded step
        self._redo: list[str] = []  # snapshots restored by redo, newest last
        self._tx_starts: list[str] = []  # snapshot at the start of each open transaction

    @property
    def text(self) -> str:
        return self._text

    # -- editing -----------------------------------------------------------

    def insert(self, pos: int, s: str) -> None:
        """Insert ``s`` at ``pos``. Raises IndexError if ``pos`` not in [0, len]."""
        if not 0 <= pos <= len(self._text):
            raise IndexError(
                f"insert position {pos} out of range [0, {len(self._text)}]"
            )
        self._commit(self._text[:pos] + s + self._text[pos:])

    def delete(self, pos: int, n: int) -> None:
        """Delete ``n`` characters starting at ``pos``.

        Raises IndexError if ``pos < 0``, ``n < 0``, or ``pos + n > len``.
        """
        self._check_range(pos, n, "delete")
        self._commit(self._text[:pos] + self._text[pos + n :])

    def replace(self, pos: int, n: int, s: str) -> None:
        """Replace the ``n`` characters starting at ``pos`` with ``s``.

        Recorded as a single undo step. Raises IndexError under the same
        conditions as ``delete``.
        """
        self._check_range(pos, n, "replace")
        self._commit(self._text[:pos] + s + self._text[pos + n :])

    def find_all(self, s: str) -> list[int]:
        """Return the start positions of every non-overlapping occurrence of ``s``.

        Matches are found left to right, so after a match at ``i`` the search
        resumes at ``i + len(s)``. Raises ValueError if ``s`` is empty.
        """
        if not s:
            raise ValueError("cannot search for an empty string")
        positions: list[int] = []
        i = self._text.find(s)
        while i != -1:
            positions.append(i)
            i = self._text.find(s, i + len(s))
        return positions

    def replace_all(self, old: str, new: str) -> int:
        """Replace every non-overlapping occurrence of ``old`` with ``new``.

        Recorded as a single undo step. Returns the number of replacements,
        which may be zero. Raises ValueError if ``old`` is empty.
        """
        count = len(self.find_all(old))
        if count:
            self._commit(self._text.replace(old, new))
        return count

    @contextmanager
    def transaction(self) -> Iterator[None]:
        """Group every edit made inside the ``with`` block into one undo step.

        If the block raises, the buffer is restored to its text at the start
        of the block, nothing is recorded in history, and the exception
        propagates. Transactions may nest; an inner block simply becomes part
        of the enclosing one, but an inner block that raises still rolls
        back to its own start. ``undo``/``redo`` may not be called inside a
        transaction.
        """
        start = self._text
        self._tx_starts.append(start)
        try:
            yield
        except BaseException:
            self._text = start
            raise
        finally:
            self._tx_starts.pop()
        self._commit(self._text, before=start)

    # -- history -----------------------------------------------------------

    def undo(self) -> bool:
        """Revert the most recent step. Returns False if there is nothing to undo."""
        self._require_no_transaction("undo")
        if not self._undo:
            return False
        self._redo.append(self._text)
        self._text = self._undo.pop()
        return True

    def redo(self) -> bool:
        """Re-apply the most recently undone step. Returns False if none."""
        self._require_no_transaction("redo")
        if not self._redo:
            return False
        self._undo.append(self._text)
        self._text = self._redo.pop()
        return True

    def can_undo(self) -> bool:
        """Whether ``undo`` would revert a step."""
        return bool(self._undo)

    def can_redo(self) -> bool:
        """Whether ``redo`` would re-apply a step."""
        return bool(self._redo)

    def undo_all(self) -> None:
        """Revert every undoable step; each one remains redoable in order."""
        while self.undo():
            pass

    def clear_history(self) -> None:
        """Forget all undo and redo history. The current text is unchanged.

        May not be called inside a transaction.
        """
        self._require_no_transaction("clear_history")
        self._undo.clear()
        self._redo.clear()

    def history_len(self) -> int:
        """Number of steps that ``undo`` can currently revert."""
        return len(self._undo)

    # -- internals ---------------------------------------------------------

    def _check_range(self, pos: int, n: int, op: str) -> None:
        if pos < 0 or n < 0 or pos + n > len(self._text):
            raise IndexError(
                f"{op} range [{pos}, {pos + n}) out of bounds for length "
                f"{len(self._text)}"
            )

    def _require_no_transaction(self, op: str) -> None:
        if self._tx_starts:
            raise RuntimeError(f"cannot {op} inside a transaction")

    def _commit(self, new_text: str, *, before: str | None = None) -> None:
        """Make ``new_text`` current and record one undo step from ``before``.

        This is the single path every edit takes. ``before`` defaults to the
        current text; a transaction passes its start snapshot instead. Inside
        an open transaction the text is updated but nothing is recorded: the
        enclosing transaction records the whole block when it commits. A step
        that leaves the text unchanged is not recorded, so undo never appears
        to do nothing. Any recorded step discards the redo history.
        """
        if before is None:
            before = self._text
        self._text = new_text
        if self._tx_starts or new_text == before:
            return
        self._undo.append(before)
        self._redo.clear()
