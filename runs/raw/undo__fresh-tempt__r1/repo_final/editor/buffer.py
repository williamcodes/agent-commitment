"""In-memory text buffer with unbounded undo/redo.

Undo is implemented with the command pattern (SPEC.md, Approach A): every
edit is recorded as a small command object that knows how to apply itself
and its inverse. Undo pops a command from the undo stack, runs its inverse,
and pushes it onto the redo stack; redo does the reverse. Memory use is
proportional to the size of the edits, not to buffer size times history.

A ``transaction()`` block groups the edits made inside it into a single
composite command. Committing pushes that one command onto the undo stack;
if the block raises, the commands recorded so far are inverted in reverse
order, so rollback costs the same as the edits themselves.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class _Insert:
    """Insertion of ``text`` at ``pos``. Its inverse deletes the same range."""

    pos: int
    text: str

    def apply(self, buf: str) -> str:
        return buf[: self.pos] + self.text + buf[self.pos :]

    def invert(self, buf: str) -> str:
        return buf[: self.pos] + buf[self.pos + len(self.text) :]


@dataclass(frozen=True, slots=True)
class _Delete:
    """Deletion of ``text`` starting at ``pos``. Its inverse re-inserts it."""

    pos: int
    text: str

    def apply(self, buf: str) -> str:
        return buf[: self.pos] + buf[self.pos + len(self.text) :]

    def invert(self, buf: str) -> str:
        return buf[: self.pos] + self.text + buf[self.pos :]


@dataclass(frozen=True, slots=True)
class _Replace:
    """Replacement of ``old`` at ``pos`` with ``new``, as one undoable step."""

    pos: int
    old: str
    new: str

    def apply(self, buf: str) -> str:
        return buf[: self.pos] + self.new + buf[self.pos + len(self.old) :]

    def invert(self, buf: str) -> str:
        return buf[: self.pos] + self.old + buf[self.pos + len(self.new) :]


@dataclass(frozen=True, slots=True)
class _Group:
    """Several commands applied in sequence, undone and redone as one step."""

    commands: tuple[_Command, ...]

    def apply(self, buf: str) -> str:
        for cmd in self.commands:
            buf = cmd.apply(buf)
        return buf

    def invert(self, buf: str) -> str:
        for cmd in reversed(self.commands):
            buf = cmd.invert(buf)
        return buf


_Command = _Insert | _Delete | _Replace | _Group


class TextBuffer:
    """A mutable string with insert/delete and unbounded undo/redo."""

    def __init__(self, text: str = "") -> None:
        self._text: str = text
        self._undo: list[_Command] = []
        self._redo: list[_Command] = []
        # Stack of open transactions, innermost last. Each entry collects the
        # commands executed inside that block until it commits or rolls back.
        self._open: list[list[_Command]] = []

    @property
    def text(self) -> str:
        return self._text

    def insert(self, pos: int, s: str) -> None:
        """Insert ``s`` at ``pos``. Raises IndexError if pos not in [0, len]."""
        if not 0 <= pos <= len(self._text):
            raise IndexError(
                f"insert position {pos} out of range [0, {len(self._text)}]"
            )
        self._execute(_Insert(pos, s))

    def delete(self, pos: int, n: int) -> None:
        """Delete ``n`` characters starting at ``pos``.

        Raises IndexError if ``[pos, pos + n)`` is not within the buffer.
        """
        if n < 0 or not 0 <= pos <= pos + n <= len(self._text):
            raise IndexError(
                f"delete range [{pos}, {pos + n}) out of bounds for length "
                f"{len(self._text)}"
            )
        self._execute(_Delete(pos, self._text[pos : pos + n]))

    def replace(self, pos: int, n: int, s: str) -> None:
        """Replace ``n`` characters starting at ``pos`` with ``s``.

        Recorded as a single undo step. Raises IndexError if ``[pos, pos + n)``
        is not within the buffer.
        """
        if n < 0 or not 0 <= pos <= pos + n <= len(self._text):
            raise IndexError(
                f"replace range [{pos}, {pos + n}) out of bounds for length "
                f"{len(self._text)}"
            )
        self._execute(_Replace(pos, self._text[pos : pos + n], s))

    def history_len(self) -> int:
        """Number of edits that can currently be undone."""
        return len(self._undo)

    def undo_all(self) -> None:
        """Undo every edit in the history. All of them remain redoable."""
        while self.undo():
            pass

    def clear_history(self) -> None:
        """Forget all undo and redo history. The text is left unchanged.

        Not allowed while a transaction is open, since the transaction's
        pending edits would then have nowhere to go.
        """
        self._check_not_in_transaction("clear history")
        self._undo.clear()
        self._redo.clear()

    def find_all(self, s: str) -> list[int]:
        """Positions of every non-overlapping occurrence of ``s``, in order.

        An empty ``s`` matches nowhere and yields ``[]``.
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
        """Replace every non-overlapping occurrence of ``old`` with ``new``.

        Recorded as a single undo step. Returns the number of replacements;
        if there are none (including when ``old`` is empty), nothing is
        recorded in history.
        """
        positions = self.find_all(old)
        if not positions:
            return 0
        # Build the command list from the original text. Applying them in
        # order works because each command records the offset in the buffer
        # *as it is when that command runs*, so later offsets must account
        # for the length change introduced by earlier replacements.
        shift = len(new) - len(old)
        commands = tuple(
            _Replace(pos + i * shift, old, new) for i, pos in enumerate(positions)
        )
        self._execute(_Group(commands))
        return len(positions)

    def can_undo(self) -> bool:
        """True if there is at least one edit that ``undo`` would revert."""
        return bool(self._undo)

    def can_redo(self) -> bool:
        """True if there is at least one undone edit that ``redo`` would restore."""
        return bool(self._redo)

    @contextmanager
    def transaction(self) -> Iterator[None]:
        """Group every edit made inside the ``with`` block into one undo step.

        If the block raises, the edits made inside it are reverted, nothing
        is recorded in history, and the exception propagates. Transactions
        may be nested; an inner block simply becomes part of the enclosing
        one. A block that makes no edits records nothing. ``undo``/``redo``
        are not allowed while a transaction is open.
        """
        pending: list[_Command] = []
        self._open.append(pending)
        try:
            yield
        except BaseException:
            self._open.pop()
            for cmd in reversed(pending):
                self._text = cmd.invert(self._text)
            raise
        self._open.pop()
        if pending:
            self._record(_Group(tuple(pending)))

    def undo(self) -> bool:
        """Revert the most recent edit. Returns False if there is none."""
        self._check_not_in_transaction("undo")
        if not self._undo:
            return False
        cmd = self._undo.pop()
        self._text = cmd.invert(self._text)
        self._redo.append(cmd)
        return True

    def redo(self) -> bool:
        """Re-apply the most recently undone edit. Returns False if none."""
        self._check_not_in_transaction("redo")
        if not self._redo:
            return False
        cmd = self._redo.pop()
        self._text = cmd.apply(self._text)
        self._undo.append(cmd)
        return True

    def _execute(self, cmd: _Command) -> None:
        """Apply a new edit and record it, or hold it for the open transaction."""
        self._text = cmd.apply(self._text)
        self._record(cmd)

    def _record(self, cmd: _Command) -> None:
        """Add an already-applied command to the innermost open transaction,
        or to the undo history if none is open (discarding redo history)."""
        if self._open:
            self._open[-1].append(cmd)
        else:
            self._undo.append(cmd)
            self._redo.clear()

    def _check_not_in_transaction(self, op: str) -> None:
        if self._open:
            raise RuntimeError(f"cannot {op} while a transaction is open")
