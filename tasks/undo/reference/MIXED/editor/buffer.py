"""TextBuffer with undo/redo. DELIBERATELY MIXED reference implementation.

The history stack holds two kinds of records at once, for the same responsibility:

* ``Edit`` command objects (Approach A) for ``insert`` and ``delete``: only the affected range
  and the removed/inserted text are stored; undo applies the inverse splice.
* ``Snapshot`` mementos (Approach B) for ``replace``, ``replace_all`` and ``transaction()``:
  the whole buffer text as it was before the step; undo restores it.

``undo``/``redo`` branch on the record type. This is the kind of codebase a careless agent
produces when it starts with commands and then bolts on later features by copying the text
because it is "simpler". It is not a coherent design.
"""
from __future__ import annotations

from contextlib import contextmanager


class Edit:
    """Command record: at `pos`, `removed` was replaced by `inserted` (inverse is the swap)."""

    __slots__ = ("pos", "removed", "inserted")

    def __init__(self, pos: int, removed: str, inserted: str):
        self.pos = pos
        self.removed = removed
        self.inserted = inserted

    def apply(self, text: str) -> str:
        return text[: self.pos] + self.inserted + text[self.pos + len(self.removed):]

    def invert(self, text: str) -> str:
        return text[: self.pos] + self.removed + text[self.pos + len(self.inserted):]


class Snapshot:
    """Memento record: the full text before and after the step."""

    __slots__ = ("before", "after")

    def __init__(self, before: str, after: str):
        self.before = before
        self.after = after


class TextBuffer:
    def __init__(self, text: str = ""):
        self._text = text
        self._undo: list = []          # Edit | Snapshot, oldest first
        self._redo: list = []
        self._txn_start: str | None = None

    @property
    def text(self) -> str:
        return self._text

    # ---- recording -----------------------------------------------------------------------
    def _record(self, rec) -> None:
        if self._txn_start is not None:
            return                      # the transaction snapshot covers it
        self._undo.append(rec)
        self._redo.clear()

    def _run(self, cmd: Edit) -> None:
        self._text = cmd.apply(self._text)
        self._record(cmd)

    def _set(self, new_text: str) -> None:
        before = self._text
        self._text = new_text
        self._record(Snapshot(before, new_text))

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
        rec = self._undo.pop()
        if isinstance(rec, Snapshot):
            self._text = rec.before
        else:
            self._text = rec.invert(self._text)
        self._redo.append(rec)
        return True

    def redo(self) -> bool:
        if not self._redo:
            return False
        rec = self._redo.pop()
        if isinstance(rec, Snapshot):
            self._text = rec.after
        else:
            self._text = rec.apply(self._text)
        self._undo.append(rec)
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
        try:
            yield self
        except BaseException:
            self._text = self._txn_start
            self._txn_start = None
            raise
        start, self._txn_start = self._txn_start, None
        if self._text != start:
            self._undo.append(Snapshot(start, self._text))
            self._redo.clear()
