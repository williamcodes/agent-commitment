from netgraph.graph import Graph


def test_remove_edge_and_degree():
    g = Graph(4)
    g.add_edge(0, 1); g.add_edge(0, 2); g.add_edge(2, 2)
    assert g.degree(0) == 2
    assert g.degree(2) == 2       # a self-loop counts once
    assert g.remove_edge(0, 1) is True
    assert g.remove_edge(0, 1) is False
    assert not g.has_edge(1, 0)
    assert g.degree(0) == 1
    assert g.edge_count() == 2


def test_connected_components():
    g = Graph(7)
    for u, v in [(0, 1), (1, 2), (3, 4), (6, 6)]:
        g.add_edge(u, v)
    comps = g.connected_components()
    assert comps == [[0, 1, 2], [3, 4], [5], [6]]
