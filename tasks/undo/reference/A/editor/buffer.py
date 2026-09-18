"""TextBuffer with undo/redo using the command pattern (Approach A).

Every edit is recorded as a small command object holding only the affected range and the
text that was removed/inserted; undo applies the inverse operation. Memory is proportional to
the size of the edits, never to the buffer size.
"""
from __future__ import annotations

from contextlib import contextmanager


class Edit:
    """A single splice command: at `pos`, `removed` was replaced by `inserted`."""

    __slots__ = ("pos", "removed", "inserted")

    def __init__(self, pos: int, removed: str, inserted: str):
        self.pos = pos
        self.removed = removed
        self.inserted = inserted

    def apply(self, text: str) -> str:
        return text[: self.pos] + self.inserted + text[self.pos + len(self.removed):]

    def invert(self, text: str) -> str:
        return text[: self.pos] + self.removed + text[self.pos + len(self.inserted):]


class CompositeEdit:
    """A group of commands undone/redone as one step."""

    __slots__ = ("edits",)

    def __init__(self, edits: list):
        self.edits = list(edits)

    def apply(self, text: str) -> str:
        for e in self.edits:
            text = e.apply(text)
        return text

    def invert(self, text: str) -> str:
        for e in reversed(self.edits):
            text = e.invert(text)
        return text


class TextBuffer:
    def __init__(self, text: str = ""):
        self._text = text
        self._undo: list = []
        self._redo: list = []
        self._txn: list | None = None

    @property
    def text(self) -> str:
        return self._text

    # ---- recording -----------------------------------------------------------------------
    def _run(self, cmd) -> None:
        self._text = cmd.apply(self._text)
        if self._txn is not None:
            self._txn.append(cmd)
        else:
            self._undo.append(cmd)
            self._redo.clear()

    # ---- edits ---------------------------------------------------------------------------
    def insert(self, pos: int, s: str) -> None:
        if pos < 0 or pos > len(self._text):
            raise IndexError(pos)
        self._run(Edit(pos, "", s))

    def delete(self, pos: int, n: int) -> None:
        if pos < 0 or n < 0 or pos + n > len(self._text):
            raise IndexError((pos, n))
        self._run(Edit(pos, self._text[pos:pos + n], ""))

    def replace(self, pos: int, n: int, s: str) -> None:
        if pos < 0 or n < 0 or pos + n > len(self._text):
            raise IndexError((pos, n))
        self._run(Edit(pos, self._text[pos:pos + n], s))

    def replace_all(self, old: str, new: str) -> int:
        positions = self.find_all(old)
        edits = []
        text = self._text
        offset = 0
        for p in positions:
            e = Edit(p + offset, old, new)
            text = e.apply(text)
            edits.append(e)
            offset += len(new) - len(old)
        if edits:
            self._run(CompositeEdit(edits))
        return len(edits)

    def find_all(self, s: str) -> list[int]:
        if not s:
            return []
        out = []
        i = self._text.find(s)
        while i != -1:
            out.append(i)
            i = self._text.find(s, i + len(s))
        return out

    # ---- history -------------------------------------------------------------------------
    def undo(self) -> bool:
        if not self._undo:
            return False
        cmd = self._undo.pop()
        self._text = cmd.invert(self._text)
        self._redo.append(cmd)
        return True

    def redo(self) -> bool:
        if not self._redo:
            return False
        cmd = self._redo.pop()
        self._text = cmd.apply(self._text)
        self._undo.append(cmd)
        return True

    def undo_all(self) -> None:
        while self.undo():
            pass

    def history_len(self) -> int:
        return len(self._undo)

    def can_undo(self) -> bool:
        return bool(self._undo)

    def can_redo(self) -> bool:
        return bool(self._redo)

    def clear_history(self) -> None:
        self._undo.clear()
        self._redo.clear()

    @contextmanager
    def transaction(self):
        if self._txn is not None:
            raise RuntimeError("nested transactions are not supported")
        self._txn = []
        try:
            yield self
        except BaseException:
            for cmd in reversed(self._txn):
                self._text = cmd.invert(self._text)
            self._txn = None
            raise
        edits, self._txn = self._txn, None
        if edits:
            self._undo.append(CompositeEdit(edits))
            self._redo.clear()
