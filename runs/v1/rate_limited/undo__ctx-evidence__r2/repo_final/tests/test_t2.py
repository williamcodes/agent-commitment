from editor.buffer import TextBuffer


def test_replace_and_undo():
    b = TextBuffer("hello world")
    b.replace(6, 5, "there")
    assert b.text == "hello there"
    assert b.undo() and b.text == "hello world"
    assert b.redo() and b.text == "hello there"


def test_history_len_and_undo_all():
    b = TextBuffer()
    b.insert(0, "a"); b.insert(1, "b"); b.insert(2, "c")
    assert b.history_len() == 3
    b.undo_all()
    assert b.text == "" and b.history_len() == 0
    assert b.redo() and b.text == "a"


def test_replace_is_single_undo_step():
    b = TextBuffer("abcd")
    b.replace(1, 2, "XYZ")
    assert b.text == "aXYZd"
    assert b.history_len() == 1
    b.undo()
    assert b.text == "abcd"
