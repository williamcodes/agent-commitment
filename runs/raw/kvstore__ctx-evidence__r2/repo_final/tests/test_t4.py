from kvstore.store import Store


def test_rename_key(tmp_path):
    s = Store(str(tmp_path / "data.kv"))
    s.set("old", "v")
    assert s.rename("old", "new") is True
    assert s.get("old") is None
    assert s.get("new") == "v"
    assert s.rename("missing", "x") is False
    s.close()


def test_rename_within_namespace_persists(tmp_path):
    path = str(tmp_path / "data.kv")
    s = Store(path)
    s.set("a", "1", ns="n1")
    s.rename("a", "b", ns="n1")
    s.close()
    s2 = Store(path)
    assert s2.keys(ns="n1") == ["b"]
    s2.close()


def test_items(tmp_path):
    s = Store(str(tmp_path / "data.kv"))
    s.set("b", "2")
    s.set("a", "1")
    s.set("z", "26", ns="n1")
    assert s.items() == [("a", "1"), ("b", "2")]
    assert s.items(ns="n1") == [("z", "26")]
    s.close()
