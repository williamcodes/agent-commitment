import os
from kvstore.store import Store


def test_set_get_roundtrip(tmp_path):
    s = Store(str(tmp_path / "data.kv"))
    s.set("a", "1")
    s.set("b", "two")
    assert s.get("a") == "1"
    assert s.get("b") == "two"
    assert s.get("missing") is None
    s.close()


def test_overwrite_and_delete(tmp_path):
    s = Store(str(tmp_path / "data.kv"))
    s.set("k", "v1")
    s.set("k", "v2")
    assert s.get("k") == "v2"
    assert s.delete("k") is True
    assert s.delete("k") is False
    assert s.get("k") is None
    s.close()


def test_keys_sorted(tmp_path):
    s = Store(str(tmp_path / "data.kv"))
    for k in ["zeta", "alpha", "mid"]:
        s.set(k, k.upper())
    assert s.keys() == ["alpha", "mid", "zeta"]
    s.close()


def test_persistence_across_instances(tmp_path):
    path = str(tmp_path / "data.kv")
    s = Store(path)
    s.set("persist", "yes")
    s.set("unicode", "héllo ✓")
    s.close()
    s2 = Store(path)
    assert s2.get("persist") == "yes"
    assert s2.get("unicode") == "héllo ✓"
    assert s2.keys() == ["persist", "unicode"]
    s2.close()


def test_single_file_only(tmp_path):
    path = str(tmp_path / "data.kv")
    s = Store(path)
    s.set("x", "y")
    s.close()
    entries = sorted(os.listdir(tmp_path))
    assert entries == ["data.kv"], entries
