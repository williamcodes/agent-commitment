from catalog.service import Catalog


def test_clone_creates_new_record_with_new_id():
    c = Catalog()
    a = c.create("A", "x")
    b = c.clone(a)
    assert b != a
    assert c.get(b)["title"] == "A" and c.get(b)["author"] == "x"
    assert [r["id"] for r in c.list()] == [a, b]


def test_bulk_create_returns_ids_in_order():
    c = Catalog()
    ids = c.bulk_create([("A", "x"), ("B", "y"), ("C", "z")])
    assert len(ids) == 3 and len(set(ids)) == 3
    assert [r["title"] for r in c.list()] == ["A", "B", "C"]
    assert [r["id"] for r in c.list()] == ids


def test_count():
    c = Catalog()
    assert c.count() == 0
    c.bulk_create([("A", "x"), ("B", "y")])
    assert c.count() == 2
