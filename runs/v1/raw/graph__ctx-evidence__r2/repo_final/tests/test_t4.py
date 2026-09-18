from netgraph.graph import Graph


def test_is_bipartite():
    g = Graph(4)
    for u, v in [(0, 1), (1, 2), (2, 3), (3, 0)]:
        g.add_edge(u, v)
    assert g.is_bipartite() is True
    g.add_edge(0, 2)
    assert g.is_bipartite() is False


def test_subgraph_preserves_order():
    g = Graph(5)
    for u, v in [(0, 1), (1, 2), (2, 3), (3, 4), (0, 4)]:
        g.add_edge(u, v)
    s = g.subgraph([4, 0, 1])     # new ids 0->4, 1->0, 2->1
    assert s.node_count() == 3
    assert s.edges() == [(0, 1), (1, 2)]


def test_common_neighbors():
    g = Graph(5)
    for u, v in [(0, 2), (1, 2), (0, 3), (1, 3), (0, 4)]:
        g.add_edge(u, v)
    assert g.common_neighbors(0, 1) == [2, 3]
