import pytest
from netgraph.graph import Graph


def test_edges_and_neighbors():
    g = Graph(5)
    g.add_edge(0, 1)
    g.add_edge(1, 2)
    g.add_edge(1, 2)     # duplicate
    g.add_edge(3, 3)     # self loop
    assert g.has_edge(0, 1) and g.has_edge(1, 0)
    assert not g.has_edge(0, 2)
    assert g.neighbors(1) == [0, 2]
    assert g.neighbors(3) == [3]
    assert g.neighbors(4) == []
    assert g.node_count() == 5
    assert g.edge_count() == 3


def test_shortest_path():
    g = Graph(6)
    for u, v in [(0, 1), (1, 2), (2, 3), (0, 4), (4, 3)]:
        g.add_edge(u, v)
    assert g.shortest_path(0, 3) in ([0, 4, 3],)
    assert g.shortest_path(0, 0) == [0]
    assert g.shortest_path(0, 5) is None
    assert len(g.shortest_path(1, 4)) == 3


def test_out_of_range():
    g = Graph(2)
    with pytest.raises(IndexError):
        g.add_edge(0, 2)
    with pytest.raises(IndexError):
        g.neighbors(-1)
    with pytest.raises(IndexError):
        g.has_edge(5, 0)
