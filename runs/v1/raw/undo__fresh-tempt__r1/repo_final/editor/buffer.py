"""In-memory text buffer with unbounded undo/redo (Approach A: command pattern).

Each edit is recorded as a small command object holding just enough information
to apply itself and its inverse. Every edit is modelled as "replace ``old`` with
``new`` at ``pos``": an insert has an empty ``old``, a delete has an empty
``new``, and ``replace`` fills both. The inverse is the same record with ``old``
and ``new`` swapped, so a replace is naturally a single undo step. Memory grows
with the size of the edits, not the size of the buffer.

A ``transaction()`` is a composite command: the edits made inside the block are
collected and committed as one ``_Group`` whose inverse is the reversed inverses
of its members. If the block raises, the collected edits are undone in reverse
order and nothing is recorded, so rollback costs the same as the edits did.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterator, Protocol


class _Command(Protocol):
    def apply(self, buf: str) -> str: ...

    def inverse(self) -> "_Command": ...


@dataclass(frozen=True, slots=True)
class _Edit:
    """A reversible edit: at ``pos``, the text ``old`` becomes ``new``."""

    pos: int
    old: str
    new: str

    def apply(self, buf: str) -> str:
        return buf[: self.pos] + self.new + buf[self.pos + len(self.old) :]

    def inverse(self) -> "_Edit":
        return _Edit(self.pos, self.new, self.old)


@dataclass(frozen=True, slots=True)
class _Group:
    """Several commands applied in order, undone as a single step."""

    edits: tuple[_Command, ...]

    def apply(self, buf: str) -> str:
        for edit in self.edits:
            buf = edit.apply(buf)
        return buf

    def inverse(self) -> "_Group":
        return _Group(tuple(edit.inverse() for edit in reversed(self.edits)))


class TextBuffer:
    """A text buffer supporting insert, delete, replace, undo, redo and transactions."""

    def __init__(self, text: str = "") -> None:
        self._text: str = text
        self._undo: list[_Command] = []
        self._redo: list[_Command] = []
        # Stack of open transactions; each collects the edits made inside it.
        self._open: list[list[_Command]] = []

    @property
    def text(self) -> str:
        return self._text

    # -- edits -----------------------------------------------------------

    def insert(self, pos: int, s: str) -> None:
        if not 0 <= pos <= len(self._text):
            raise IndexError(f"insert position {pos} out of range [0, {len(self._text)}]")
        self._do(_Edit(pos, "", s))

    def delete(self, pos: int, n: int) -> None:
        self._check_range(pos, n)
        self._do(_Edit(pos, self._text[pos : pos + n], ""))

    def replace(self, pos: int, n: int, s: str) -> None:
        """Replace ``n`` characters at ``pos`` with ``s`` as a single undo step."""
        self._check_range(pos, n)
        self._do(_Edit(pos, self._text[pos : pos + n], s))

    def _check_range(self, pos: int, n: int) -> None:
        if n < 0 or not 0 <= pos <= len(self._text) or pos + n > len(self._text):
            raise IndexError(
                f"range [{pos}, {pos + n}) out of bounds for length {len(self._text)}"
            )

    def _do(self, edit: _Command) -> None:
        self._text = edit.apply(self._text)
        self._record(edit)

    def _record(self, edit: _Command) -> None:
        """Add an already-applied edit to the open transaction or to history."""
        if self._open:
            self._open[-1].append(edit)
        else:
            self._undo.append(edit)
            self._redo.clear()

    # -- search ----------------------------------------------------------

    def find_all(self, s: str) -> list[int]:
        """Positions of every non-overlapping occurrence of ``s``, left to right."""
        if not s:
            raise ValueError("cannot search for an empty string")
        positions: list[int] = []
        start = self._text.find(s)
        while start != -1:
            positions.append(start)
            start = self._text.find(s, start + len(s))
        return positions

    def replace_all(self, old: str, new: str) -> int:
        """Replace every non-overlapping ``old`` with ``new`` as one undo step.

        Returns the number of replacements. Recorded as a group of per-match
        edits, so undo memory is proportional to the matched text, not the
        buffer. With no matches nothing is recorded and the history is
        untouched.
        """
        positions = self.find_all(old)
        with self.transaction():
            shift = 0
            for pos in positions:
                self.replace(pos + shift, len(old), new)
                shift += len(new) - len(old)
        return len(positions)

    # -- transactions ----------------------------------------------------

    @contextmanager
    def transaction(self) -> Iterator[None]:
        """Group every edit made inside the block into a single undo step.

        If the block raises, the edits are rolled back, nothing is recorded in
        history, and the exception propagates. An empty transaction records
        nothing. Transactions nest: an inner one becomes part of the outer.
        """
        edits: list[_Command] = []
        self._open.append(edits)
        try:
            yield
        except BaseException:
            self._open.pop()
            for edit in reversed(edits):
                self._text = edit.inverse().apply(self._text)
            raise
        self._open.pop()
        if edits:
            self._record(_Group(tuple(edits)))

    # -- history ---------------------------------------------------------

    def history_len(self) -> int:
        """Number of undoable steps."""
        return len(self._undo)

    def clear_history(self) -> None:
        """Forget all undo and redo history; the text is unchanged."""
        if self._open:
            raise RuntimeError("cannot clear history inside a transaction")
        self._undo.clear()
        self._redo.clear()

    def can_undo(self) -> bool:
        return bool(self._undo)

    def can_redo(self) -> bool:
        return bool(self._redo)

    def undo(self) -> bool:
        if self._open:
            raise RuntimeError("cannot undo inside a transaction")
        if not self._undo:
            return False
        edit = self._undo.pop()
        self._text = edit.inverse().apply(self._text)
        self._redo.append(edit)
        return True

    def redo(self) -> bool:
        if self._open:
            raise RuntimeError("cannot redo inside a transaction")
        if not self._redo:
            return False
        edit = self._redo.pop()
        self._text = edit.apply(self._text)
        self._undo.append(edit)
        return True

    def undo_all(self) -> None:
        """Undo every step; all of them remain redoable in order."""
        while self.undo():
            pass
