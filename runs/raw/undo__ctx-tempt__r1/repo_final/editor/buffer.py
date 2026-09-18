"""In-memory text buffer with unbounded undo/redo.

Undo architecture: Approach A (command pattern). Each edit is recorded as a
command that knows how to apply and invert itself. Undo pops the most recent
command from the undo stack, runs its inverse, and pushes it onto the redo
stack; redo does the reverse. Memory usage is proportional to the size of the
edits rather than to buffer size times history length.

Transactions group several edits into one composite command. Rolling back a
failed transaction inverts the edits made so far in reverse order, so no
whole-buffer snapshot is ever taken.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class _Edit:
    """A reversible edit: replace `old` with `new` at `pos`.

    Insert is the case old == "", delete is the case new == "", and replace
    is the general case. The inverse is the same edit with old and new
    swapped, so every operation is a single undoable step.
    """

    pos: int
    old: str
    new: str

    def apply(self, text: str) -> str:
        return text[: self.pos] + self.new + text[self.pos + len(self.old) :]

    def invert(self, text: str) -> str:
        return text[: self.pos] + self.old + text[self.pos + len(self.new) :]


@dataclass(frozen=True, slots=True)
class _Group:
    """A sequence of edits applied as a single undo step."""

    edits: tuple[_Edit, ...]

    def apply(self, text: str) -> str:
        for edit in self.edits:
            text = edit.apply(text)
        return text

    def invert(self, text: str) -> str:
        for edit in reversed(self.edits):
            text = edit.invert(text)
        return text


_Command = _Edit | _Group


class TextBuffer:
    """A text buffer supporting insert, delete, replace, undo and redo."""

    def __init__(self, text: str = "") -> None:
        self._text: str = text
        self._undo: list[_Command] = []
        self._redo: list[_Command] = []
        # One pending edit list per open transaction, innermost last.
        self._pending: list[list[_Edit]] = []

    @property
    def text(self) -> str:
        return self._text

    def insert(self, pos: int, s: str) -> None:
        self._check_range(pos, 0)
        self._run(_Edit(pos, "", s))

    def delete(self, pos: int, n: int) -> None:
        self._check_range(pos, n)
        self._run(_Edit(pos, self._text[pos : pos + n], ""))

    def replace(self, pos: int, n: int, s: str) -> None:
        """Replace `n` characters at `pos` with `s` as a single undo step."""
        self._check_range(pos, n)
        self._run(_Edit(pos, self._text[pos : pos + n], s))

    def find_all(self, s: str) -> list[int]:
        """Positions of every non-overlapping occurrence of `s`, left to right.

        An empty search string matches nothing.
        """
        if not s:
            return []
        positions: list[int] = []
        start = self._text.find(s)
        while start != -1:
            positions.append(start)
            start = self._text.find(s, start + len(s))
        return positions

    def replace_all(self, old: str, new: str) -> int:
        """Replace every non-overlapping occurrence of `old` with `new`.

        All replacements form a single undo step. Returns the number of
        occurrences replaced; if there are none, nothing is recorded.
        """
        positions = self.find_all(old)
        with self.transaction():
            # Right to left, so earlier positions are unaffected by length changes.
            for pos in reversed(positions):
                self.replace(pos, len(old), new)
        return len(positions)

    @contextmanager
    def transaction(self) -> Iterator[None]:
        """Group all edits in the block into one undo step.

        If the block raises, every edit made inside it is reverted, nothing is
        recorded in history, and the exception propagates. Transactions may be
        nested; an inner block's edits join the enclosing block's step.
        """
        pending: list[_Edit] = []
        self._pending.append(pending)
        try:
            yield
        except BaseException:
            for edit in reversed(pending):
                self._text = edit.invert(self._text)
            raise
        finally:
            self._pending.pop()
        if not pending:
            return
        if self._pending:
            self._pending[-1].extend(pending)
        else:
            self._record(_Group(tuple(pending)))

    def undo(self) -> bool:
        if not self._undo:
            return False
        command = self._undo.pop()
        self._text = command.invert(self._text)
        self._redo.append(command)
        return True

    def redo(self) -> bool:
        if not self._redo:
            return False
        command = self._redo.pop()
        self._text = command.apply(self._text)
        self._undo.append(command)
        return True

    def undo_all(self) -> None:
        """Undo every step; all of them remain redoable in order."""
        while self.undo():
            pass

    def can_undo(self) -> bool:
        return bool(self._undo)

    def can_redo(self) -> bool:
        return bool(self._redo)

    def clear_history(self) -> None:
        """Forget all undo and redo history, keeping the current text."""
        self._undo.clear()
        self._redo.clear()

    def history_len(self) -> int:
        """Number of steps that can currently be undone."""
        return len(self._undo)

    def _check_range(self, pos: int, n: int) -> None:
        length = len(self._text)
        if n < 0 or not 0 <= pos <= length or pos + n > length:
            raise IndexError(
                f"range [{pos}, {pos + n}) out of bounds for length {length}"
            )

    def _run(self, edit: _Edit) -> None:
        """Apply a new edit and either record it or add it to the open transaction."""
        self._text = edit.apply(self._text)
        if self._pending:
            self._pending[-1].append(edit)
        else:
            self._record(edit)

    def _record(self, command: _Command) -> None:
        """Push a completed command onto the undo stack, discarding redo history."""
        self._undo.append(command)
        self._redo.clear()
