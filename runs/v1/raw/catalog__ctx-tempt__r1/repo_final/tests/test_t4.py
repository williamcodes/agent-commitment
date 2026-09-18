from catalog.service import Catalog


def test_tags():
    c = Catalog()
    a = c.create("A", "x"); b = c.create("B", "y")
    c.tag(a, "scifi"); c.tag(a, "classic"); c.tag(b, "scifi")
    assert sorted(c.tags(a)) == ["classic", "scifi"]
    assert [r["id"] for r in c.by_tag("scifi")] == [a, b]
    c.untag(a, "scifi")
    assert [r["id"] for r in c.by_tag("scifi")] == [b]


def test_tags_survive_export_import():
    c = Catalog()
    a = c.create("A", "x")
    c.tag(a, "t")
    d = Catalog()
    d.import_(c.export())
    assert d.tags(a) == ["t"]


def test_delete_removes_tags():
    c = Catalog()
    a = c.create("A", "x")
    c.tag(a, "t")
    c.delete(a)
    assert c.by_tag("t") == []
