import json
from catalog.service import Catalog


def test_export_import_roundtrip():
    c = Catalog()
    a = c.create("A", "x"); b = c.create("B", "y")
    dump = c.export()
    data = json.loads(dump)
    assert [r["id"] for r in data] == [a, b]
    d = Catalog()
    d.import_(dump)
    assert d.list() == c.list()


def test_find_substring_case_insensitive():
    c = Catalog()
    c.create("The Left Hand of Darkness", "Le Guin")
    c.create("Left Behind", "x")
    c.create("Dune", "Herbert")
    assert [r["title"] for r in c.find("left")] == ["The Left Hand of Darkness", "Left Behind"]
    assert c.find("zzz") == []
