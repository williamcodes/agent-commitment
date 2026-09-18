"""In-memory text buffer with unbounded undo/redo (command pattern)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class _Insert:
    pos: int
    s: str

    def apply(self, text: str) -> str:
        return text[: self.pos] + self.s + text[self.pos :]

    def inverse(self) -> "_Delete":
        return _Delete(self.pos, self.s)


@dataclass(frozen=True)
class _Delete:
    pos: int
    s: str  # the removed text, retained so the inverse can re-insert it

    def apply(self, text: str) -> str:
        return text[: self.pos] + text[self.pos + len(self.s) :]

    def inverse(self) -> _Insert:
        return _Insert(self.pos, self.s)


@dataclass(frozen=True)
class _Replace:
    pos: int
    old: str  # the text removed, retained so the inverse can restore it
    new: str

    def apply(self, text: str) -> str:
        return text[: self.pos] + self.new + text[self.pos + len(self.old) :]

    def inverse(self) -> "_Replace":
        return _Replace(self.pos, self.new, self.old)


_Command = _Insert | _Delete | _Replace


class TextBuffer:
    def __init__(self, text: str = ""):
        self._text = text
        self._undo: list[_Command] = []
        self._redo: list[_Command] = []

    @property
    def text(self) -> str:
        return self._text

    def insert(self, pos: int, s: str) -> None:
        if not 0 <= pos <= len(self._text):
            raise IndexError(f"insert position {pos} out of range [0, {len(self._text)}]")
        self._execute(_Insert(pos, s))

    def delete(self, pos: int, n: int) -> None:
        if n < 0 or not 0 <= pos <= len(self._text) or pos + n > len(self._text):
            raise IndexError(f"delete range [{pos}, {pos + n}) out of bounds for length {len(self._text)}")
        self._execute(_Delete(pos, self._text[pos : pos + n]))

    def replace(self, pos: int, n: int, s: str) -> None:
        """Replace ``n`` characters at ``pos`` with ``s`` as a single undo step."""
        if n < 0 or not 0 <= pos <= len(self._text) or pos + n > len(self._text):
            raise IndexError(f"replace range [{pos}, {pos + n}) out of bounds for length {len(self._text)}")
        self._execute(_Replace(pos, self._text[pos : pos + n], s))

    def history_len(self) -> int:
        """Number of undoable steps."""
        return len(self._undo)

    def undo_all(self) -> None:
        """Undo every step; all of them remain redoable in order."""
        while self.undo():
            pass

    def undo(self) -> bool:
        if not self._undo:
            return False
        cmd = self._undo.pop()
        self._text = cmd.inverse().apply(self._text)
        self._redo.append(cmd)
        return True

    def redo(self) -> bool:
        if not self._redo:
            return False
        cmd = self._redo.pop()
        self._text = cmd.apply(self._text)
        self._undo.append(cmd)
        return True

    def _execute(self, cmd: _Command) -> None:
        self._text = cmd.apply(self._text)
        self._undo.append(cmd)
        self._redo.clear()
