from kvstore.store import Store


def test_namespaces_isolate_keys(tmp_path):
    s = Store(str(tmp_path / "data.kv"))
    s.set("k", "default-value")
    s.set("k", "ns-value", ns="other")
    assert s.get("k") == "default-value"
    assert s.get("k", ns="other") == "ns-value"
    assert s.get("k", ns="third") is None
    s.close()


def test_keys_and_count_per_namespace(tmp_path):
    s = Store(str(tmp_path / "data.kv"))
    s.set("a", "1", ns="n1")
    s.set("b", "2", ns="n1")
    s.set("c", "3", ns="n2")
    assert s.keys(ns="n1") == ["a", "b"]
    assert s.keys(ns="n2") == ["c"]
    assert s.keys() == []
    assert s.count(ns="n1") == 2
    assert s.count(ns="n2") == 1
    assert s.count() == 0
    s.close()


def test_namespace_delete_and_persist(tmp_path):
    path = str(tmp_path / "data.kv")
    s = Store(path)
    s.set("a", "1", ns="n1")
    assert s.delete("a") is False
    assert s.delete("a", ns="n1") is True
    s.set("b", "2", ns="n1")
    s.close()
    s2 = Store(path)
    assert s2.keys(ns="n1") == ["b"]
    assert s2.namespaces() == ["n1"]
    s2.close()
