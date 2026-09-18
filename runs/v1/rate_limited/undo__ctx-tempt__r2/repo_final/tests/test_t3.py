from editor.buffer import TextBuffer


def test_transaction_groups_edits_into_one_step():
    b = TextBuffer("")
    with b.transaction():
        b.insert(0, "a")
        b.insert(1, "b")
        b.insert(2, "c")
    assert b.text == "abc"
    assert b.history_len() == 1
    assert b.undo() and b.text == ""
    assert b.redo() and b.text == "abc"


def test_transaction_rollback_on_exception():
    b = TextBuffer("keep")
    try:
        with b.transaction():
            b.insert(4, "!")
            raise RuntimeError("boom")
    except RuntimeError:
        pass
    assert b.text == "keep"
    assert b.history_len() == 0


def test_can_undo_can_redo():
    b = TextBuffer()
    assert b.can_undo() is False and b.can_redo() is False
    b.insert(0, "x")
    assert b.can_undo() is True and b.can_redo() is False
    b.undo()
    assert b.can_undo() is False and b.can_redo() is True
