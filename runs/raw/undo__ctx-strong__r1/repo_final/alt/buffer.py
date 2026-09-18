"""TextBuffer with undo/redo using mementos (Approach B).

Before every edit the whole buffer text is pushed onto the undo stack; undo restores the
previous text and moves the current one onto the redo stack.
"""
from __future__ import annotations

from contextlib import contextmanager


class TextBuffer:
    def __init__(self, text: str = ""):
        self._text = text
        self._undo: list[str] = []      # full-text snapshots, oldest first
        self._redo: list[str] = []
        self._txn_start: str | None = None
        self._txn_dirty = False

    @property
    def text(self) -> str:
        return self._text

    # ---- recording -----------------------------------------------------------------------
    def _set(self, new_text: str) -> None:
        if self._txn_start is not None:
            self._txn_dirty = True
        else:
            self._undo.append(self._text)
            self._redo.clear()
        self._text = new_text

    # ---- edits ---------------------------------------------------------------------------
    def insert(self, pos: int, s: str) -> None:
        if pos < 0 or pos > len(self._text):
            raise IndexError(pos)
        self._set(self._text[:pos] + s + self._text[pos:])

    def delete(self, pos: int, n: int) -> None:
        if pos < 0 or n < 0 or pos + n > len(self._text):
            raise IndexError((pos, n))
        self._set(self._text[:pos] + self._text[pos + n:])

    def replace(self, pos: int, n: int, s: str) -> None:
        if pos < 0 or n < 0 or pos + n > len(self._text):
            raise IndexError((pos, n))
        self._set(self._text[:pos] + s + self._text[pos + n:])

    def replace_all(self, old: str, new: str) -> int:
        if not old:
            return 0
        n = self._text.count(old)
        if n:
            self._set(self._text.replace(old, new))
        return n

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
        self._redo.append(self._text)
        self._text = self._undo.pop()
        return True

    def redo(self) -> bool:
        if not self._redo:
            return False
        self._undo.append(self._text)
        self._text = self._redo.pop()
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
        if self._txn_start is not None:
            raise RuntimeError("nested transactions are not supported")
        self._txn_start = self._text
        self._txn_dirty = False
        try:
            yield self
        except BaseException:
            self._text = self._txn_start
            self._txn_start = None
            raise
        start, self._txn_start = self._txn_start, None
        if self._txn_dirty:
            self._undo.append(start)
            self._redo.clear()
