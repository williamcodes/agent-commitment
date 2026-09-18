import pytest
from editor.buffer import TextBuffer


def test_insert_delete():
    b = TextBuffer("hello")
    b.insert(5, " world")
    assert b.text == "hello world"
    b.delete(0, 6)
    assert b.text == "world"


def test_undo_redo_sequence():
    b = TextBuffer()
    b.insert(0, "abc")
    b.insert(3, "def")
    b.delete(0, 2)
    assert b.text == "cdef"
    assert b.undo() and b.text == "abcdef"
    assert b.undo() and b.text == "abc"
    assert b.redo() and b.text == "abcdef"
    assert b.redo() and b.text == "cdef"
    assert b.redo() is False
    assert b.undo() and b.undo() and b.undo() and b.text == ""
    assert b.undo() is False


def test_new_edit_clears_redo():
    b = TextBuffer("x")
    b.insert(1, "y")
    b.undo()
    b.insert(1, "z")
    assert b.redo() is False
    assert b.text == "xz"


def test_bounds():
    b = TextBuffer("abc")
    with pytest.raises(IndexError):
        b.insert(4, "x")
    with pytest.raises(IndexError):
        b.delete(2, 5)
    with pytest.raises(IndexError):
        b.delete(-1, 1)
    assert b.text == "abc"
