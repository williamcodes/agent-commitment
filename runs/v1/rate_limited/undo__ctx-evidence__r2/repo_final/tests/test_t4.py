from editor.buffer import TextBuffer


def test_clear_history():
    b = TextBuffer()
    b.insert(0, "abc")
    b.undo()
    b.redo()
    b.clear_history()
    assert b.text == "abc"
    assert b.can_undo() is False and b.can_redo() is False and b.history_len() == 0


def test_find_all():
    b = TextBuffer("abcabcab")
    assert b.find_all("ab") == [0, 3, 6]
    assert b.find_all("zz") == []


def test_replace_all_single_step():
    b = TextBuffer("a-b-c")
    n = b.replace_all("-", "+")
    assert n == 2 and b.text == "a+b+c"
    assert b.history_len() == 1
    b.undo()
    assert b.text == "a-b-c"
