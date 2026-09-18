import json
from kvstore.store import Store


def test_search_substring_in_keys(tmp_path):
    s = Store(str(tmp_path / "data.kv"))
    for k in ["apple", "pineapple", "banana", "grape"]:
        s.set(k, "x")
    assert s.search("apple") == ["apple", "pineapple"]
    assert s.search("an") == ["banana"]
    assert s.search("zzz") == []
    s.close()


def test_search_respects_namespace(tmp_path):
    s = Store(str(tmp_path / "data.kv"))
    s.set("apple", "x", ns="fruit")
    s.set("applesauce", "x", ns="food")
    assert s.search("apple", ns="fruit") == ["apple"]
    assert s.search("apple", ns="food") == ["applesauce"]
    s.close()


def test_export_and_import_json(tmp_path):
    s = Store(str(tmp_path / "data.kv"))
    s.set("a", "1")
    s.set("b", "2", ns="n1")
    out = tmp_path / "dump.json"
    s.export_json(str(out))
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data == {"default": {"a": "1"}, "n1": {"b": "2"}}
    s.close()

    t = Store(str(tmp_path / "other.kv"))
    t.import_json(str(out))
    assert t.get("a") == "1"
    assert t.get("b", ns="n1") == "2"
    assert t.namespaces() == ["default", "n1"]
    t.close()
