"""In-memory text buffer with unbounded undo/redo.

Undo architecture: Approach A (command pattern). Each edit is recorded as a
small command object that knows how to apply and invert itself, so history
memory scales with the size of the edits rather than the size of the buffer.
A transaction groups several commands into one composite command.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class _Command:
    """A reversible edit: at ``pos``, the text ``old`` is replaced by ``new``.

    Inserts have an empty ``old``, deletes have an empty ``new``, and replaces
    have both. The inverse simply swaps ``old`` and ``new``.
    """

    pos: int
    old: str
    new: str

    def apply(self, text: str) -> str:
        return text[: self.pos] + self.new + text[self.pos + len(self.old) :]

    def inverse(self) -> _Command:
        return _Command(self.pos, self.new, self.old)


@dataclass(frozen=True, slots=True)
class _Composite:
    """Several edits recorded as a single undo step (the result of a transaction)."""

    steps: tuple[_Edit, ...]

    def apply(self, text: str) -> str:
        for step in self.steps:
            text = step.apply(text)
        return text

    def inverse(self) -> _Composite:
        return _Composite(tuple(step.inverse() for step in reversed(self.steps)))


_Edit = _Command | _Composite


class TextBuffer:
    """A text buffer supporting insert, delete, replace, transactions and undo/redo."""

    def __init__(self, text: str = "") -> None:
        self._text: str = text
        self._undo: list[_Edit] = []
        self._redo: list[_Edit] = []
        # One pending list per open transaction, innermost last.
        self._txn_stack: list[list[_Edit]] = []

    @property
    def text(self) -> str:
        return self._text

    # ---- edits --------------------------------------------------------------

    def insert(self, pos: int, s: str) -> None:
        if not 0 <= pos <= len(self._text):
            raise IndexError(f"insert position {pos} out of range [0, {len(self._text)}]")
        self._execute(_Command(pos, "", s))

    def delete(self, pos: int, n: int) -> None:
        self._check_range(pos, n, "delete")
        self._execute(_Command(pos, self._text[pos : pos + n], ""))

    def replace(self, pos: int, n: int, s: str) -> None:
        """Replace ``n`` characters at ``pos`` with ``s`` as a single undo step."""
        self._check_range(pos, n, "replace")
        self._execute(_Command(pos, self._text[pos : pos + n], s))

    def find_all(self, s: str) -> list[int]:
        """Positions of every non-overlapping occurrence of ``s``, left to right."""
        if not s:
            return []
        out: list[int] = []
        i = self._text.find(s)
        while i != -1:
            out.append(i)
            i = self._text.find(s, i + len(s))
        return out

    def replace_all(self, old: str, new: str) -> int:
        """Replace every non-overlapping occurrence of ``old`` with ``new``.

        All replacements form a single undo step. Returns the number replaced.
        An empty ``old`` matches nothing and returns 0.
        """
        positions = self.find_all(old)
        if not positions:
            return 0
        # Edit right to left so earlier positions stay valid as lengths change.
        with self.transaction():
            for pos in reversed(positions):
                self.replace(pos, len(old), new)
        return len(positions)

    @contextmanager
    def transaction(self) -> Iterator[TextBuffer]:
        """Group all edits in the block into one undo step.

        If the block raises, every edit made inside it is rolled back, nothing
        is recorded in history, and the exception propagates. A block that
        makes no edits records nothing. Transactions may be nested; an inner
        block becomes a single step of the enclosing one.
        """
        pending: list[_Edit] = []
        self._txn_stack.append(pending)
        try:
            yield self
        except BaseException:
            for step in reversed(pending):
                self._text = step.inverse().apply(self._text)
            raise
        finally:
            self._txn_stack.pop()
        if pending:
            self._record(_Composite(tuple(pending)))

    # ---- history ------------------------------------------------------------

    def undo(self) -> bool:
        self._check_no_transaction("undo")
        if not self._undo:
            return False
        cmd = self._undo.pop()
        self._text = cmd.inverse().apply(self._text)
        self._redo.append(cmd)
        return True

    def redo(self) -> bool:
        self._check_no_transaction("redo")
        if not self._redo:
            return False
        cmd = self._redo.pop()
        self._text = cmd.apply(self._text)
        self._undo.append(cmd)
        return True

    def undo_all(self) -> None:
        """Undo every step; all of them remain redoable in order."""
        while self.undo():
            pass

    def history_len(self) -> int:
        """Number of steps that can currently be undone."""
        return len(self._undo)

    def can_undo(self) -> bool:
        return bool(self._undo)

    def can_redo(self) -> bool:
        return bool(self._redo)

    def clear_history(self) -> None:
        """Forget all undo and redo history. The text is unchanged."""
        self._undo.clear()
        self._redo.clear()

    # ---- internals ----------------------------------------------------------

    def _check_range(self, pos: int, n: int, op: str) -> None:
        if n < 0 or not 0 <= pos <= len(self._text) or pos + n > len(self._text):
            raise IndexError(
                f"{op} range [{pos}, {pos + n}) out of bounds for length {len(self._text)}"
            )

    def _check_no_transaction(self, op: str) -> None:
        if self._txn_stack:
            raise RuntimeError(f"cannot {op} inside an open transaction")

    def _execute(self, cmd: _Command) -> None:
        """Apply a fresh edit and record it (or add it to the open transaction)."""
        self._text = cmd.apply(self._text)
        self._record(cmd)

    def _record(self, edit: _Edit) -> None:
        if self._txn_stack:
            self._txn_stack[-1].append(edit)
        else:
            self._undo.append(edit)
            self._redo.clear()
