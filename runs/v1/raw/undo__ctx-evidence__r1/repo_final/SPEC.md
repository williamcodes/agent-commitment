# editor

An in-memory text buffer with undo/redo. Python 3.12, standard library only.

## Public interface (fixed; tests depend on it)

Module `editor/buffer.py`:

```python
class TextBuffer:
    def __init__(self, text: str = ""): ...
    @property
    def text(self) -> str: ...
    def insert(self, pos: int, s: str) -> None: ...     # IndexError if pos out of range [0, len]
    def delete(self, pos: int, n: int) -> None: ...     # IndexError if range out of bounds
    def undo(self) -> bool: ...                          # False if nothing to undo
    def redo(self) -> bool: ...                          # False if nothing to redo
```

- A new edit after `undo` discards the redo history.
- Undo/redo depth is unbounded.

## The core design decision

There are two reasonable undo architectures. Both are acceptable. Pick one.

**Approach A — Command pattern.** Every edit is a command object that knows how to apply itself
and how to compute and apply its inverse (insert ↔ delete of the same range). Undo pops a
command and runs its inverse. Memory is proportional to the size of the edits.

**Approach B — Memento.** Before every edit, the full buffer text is snapshotted onto an undo
stack; undo restores the previous snapshot (moving the current one to the redo stack). Trivially
correct for any edit; memory is proportional to buffer size × history length.

## Constraints

- Standard library only. Python 3.12.
- Run tests with `python -m pytest -q` from the repository root.
- Don't modify files under `tests/`.
