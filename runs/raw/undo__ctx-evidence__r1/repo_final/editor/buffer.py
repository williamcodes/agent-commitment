"""In-memory text buffer with unbounded undo/redo.

Undo is implemented with the memento pattern (Approach B in SPEC.md). Before
every top-level edit the current text is pushed onto the undo stack; undo
moves the current text to the redo stack and restores the previous snapshot.

This was originally a command-pattern implementation (Approach A). It was
switched to snapshots because the buffer must support ``apply_plugin(fn)``,
where ``fn`` is an opaque ``text -> text`` function with no inverse and no
permitted diff. A snapshot is the only thing that can undo such an edit, and
using snapshots for every edit keeps a single uniform undo mechanism instead
of special-casing plugins. The cost is memory proportional to buffer size ×
history length rather than to edit size. Python strings are immutable, so a
snapshot is a reference, not a copy, until the text actually changes.

Transactions fall out naturally: snapshot at block start, push that one
snapshot as a single step on success, restore it on failure.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator


class TextBuffer:
    """A text buffer supporting insert, delete, replace, search, transactions, undo and redo."""

    def __init__(self, text: str = "") -> None:
        self._text: str = text
        self._undo: list[str] = []   # snapshots of text before each undoable step
        self._redo: list[str] = []   # snapshots of text before each redoable step
        self._txn: list[str] = []    # snapshot at the start of each open transaction

    @property
    def text(self) -> str:
        return self._text

    # -- editing ------------------------------------------------------------

    def insert(self, pos: int, s: str) -> None:
        """Insert ``s`` at ``pos``. ``pos`` must be in ``[0, len(text)]``."""
        self._check_range(pos, 0)
        self._set(self._text[:pos] + s + self._text[pos:])

    def delete(self, pos: int, n: int) -> None:
        """Delete ``n`` characters starting at ``pos``.

        Raises ``IndexError`` if ``pos`` or ``pos + n`` falls outside the
        buffer, or if ``n`` is negative.
        """
        self.replace(pos, n, "")

    def replace(self, pos: int, n: int, s: str) -> None:
        """Replace ``n`` characters at ``pos`` with ``s`` as a single undo step.

        Bounds are checked exactly as for ``delete``.
        """
        self._check_range(pos, n)
        self._set(self._text[:pos] + s + self._text[pos + n :])

    def find_all(self, s: str) -> list[int]:
        """Positions of all non-overlapping occurrences of ``s``, left to right."""
        if not s:
            raise ValueError("search string must be non-empty")
        positions: list[int] = []
        i = self._text.find(s)
        while i != -1:
            positions.append(i)
            i = self._text.find(s, i + len(s))
        return positions

    def replace_all(self, old: str, new: str) -> int:
        """Replace every non-overlapping occurrence of ``old`` with ``new``.

        Performed as a single undo step. Returns the number of replacements;
        if there were none, nothing is recorded in history.
        """
        if not old:
            raise ValueError("search string must be non-empty")
        count = self._text.count(old)
        if count:
            self._set(self._text.replace(old, new))
        return count

    def _check_range(self, pos: int, n: int) -> None:
        length = len(self._text)
        if n < 0:
            raise IndexError(f"length {n} must be non-negative")
        if not 0 <= pos <= length or pos + n > length:
            raise IndexError(f"range [{pos}, {pos + n}) out of bounds for length {length}")

    def _set(self, new_text: str) -> None:
        """Make ``new_text`` current, recording an undo step unless inside a transaction."""
        if not self._txn:
            self._undo.append(self._text)
            self._redo.clear()
        self._text = new_text

    # -- transactions ---------------------------------------------------------

    @contextmanager
    def transaction(self) -> Iterator[None]:
        """Group all edits in the block into one undo step.

        If the block raises, the buffer is restored to its state at the start
        of the block, nothing is recorded in history, and the exception
        propagates. Transactions may nest; only the outermost one records a
        history step, and an inner failure rolls back just its own edits.
        """
        start = self._text
        self._txn.append(start)
        try:
            yield
        except BaseException:
            self._text = start
            raise
        else:
            if len(self._txn) == 1 and self._text != start:
                self._undo.append(start)
                self._redo.clear()
        finally:
            self._txn.pop()

    # -- history ------------------------------------------------------------

    def clear_history(self) -> None:
        """Forget all undo and redo history. The current text is kept."""
        self._undo.clear()
        self._redo.clear()

    def history_len(self) -> int:
        """Number of steps that can currently be undone."""
        return len(self._undo)

    def can_undo(self) -> bool:
        return bool(self._undo)

    def can_redo(self) -> bool:
        return bool(self._redo)

    def undo(self) -> bool:
        """Revert the most recent step. Returns False if there is nothing to undo."""
        if not self._undo:
            return False
        self._redo.append(self._text)
        self._text = self._undo.pop()
        return True

    def undo_all(self) -> None:
        """Undo every step in the history. Each step remains redoable."""
        while self.undo():
            pass

    def redo(self) -> bool:
        """Re-apply the most recently undone step. Returns False if nothing to redo."""
        if not self._redo:
            return False
        self._undo.append(self._text)
        self._text = self._redo.pop()
        return True
