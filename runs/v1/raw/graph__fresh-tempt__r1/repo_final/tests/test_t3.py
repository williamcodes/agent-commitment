from netgraph.graph import Graph


def test_add_node_grows_graph():
    g = Graph(2)
    g.add_edge(0, 1)
    new = g.add_node()
    assert new == 2 and g.node_count() == 3
    g.add_edge(2, 0)
    assert g.neighbors(0) == [1, 2]


def test_remove_node_relabels_higher_nodes():
    g = Graph(4)
    for u, v in [(0, 1), (1, 2), (2, 3), (0, 3)]:
        g.add_edge(u, v)
    g.remove_node(1)             # nodes 2,3 become 1,2
    assert g.node_count() == 3
    assert g.edge_count() == 2
    assert g.has_edge(1, 2)      # old (2,3)
    assert g.has_edge(0, 2)      # old (0,3)
    assert g.neighbors(0) == [2]


def test_to_edge_list_sorted():
    g = Graph(3)
    g.add_edge(2, 0); g.add_edge(1, 1); g.add_edge(0, 1)
    assert g.edges() == [(0, 1), (0, 2), (1, 1)]
