import pytest
from catalog.service import Catalog, NotFound


def test_create_get():
    c = Catalog()
    rid = c.create("Dune", "Herbert")
    assert isinstance(rid, str) and rid
    assert c.get(rid) == {"id": rid, "title": "Dune", "author": "Herbert"}


def test_ids_unique_and_stable():
    c = Catalog()
    ids = [c.create(f"t{i}", "a") for i in range(50)]
    assert len(set(ids)) == 50
    c.update(ids[3], title="changed")
    assert c.get(ids[3])["id"] == ids[3]


def test_update_and_delete():
    c = Catalog()
    rid = c.create("A", "B")
    assert c.update(rid, title="A2")["title"] == "A2"
    with pytest.raises(ValueError):
        c.update(rid, isbn="x")
    c.delete(rid)
    with pytest.raises(NotFound):
        c.get(rid)
    with pytest.raises(NotFound):
        c.delete(rid)


def test_list_in_creation_order():
    c = Catalog()
    a = c.create("A", "x"); b = c.create("B", "y"); d = c.create("D", "z")
    c.delete(b)
    assert [r["id"] for r in c.list()] == [a, d]
