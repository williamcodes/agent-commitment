"""Undirected graph backed by adjacency sets (Approach A in SPEC.md)."""

from __future__ import annotations

from collections import deque


class Graph:
    """A simple undirected graph on nodes ``0 … nodes-1``.

    Each node keeps a ``set`` of its neighbours, so memory is proportional to
    nodes + edges and neighbour iteration is proportional to degree. Self-loops
    are allowed and stored once (``u in adj[u]``).
    """

    def __init__(self, nodes: int) -> None:
        if not isinstance(nodes, int) or isinstance(nodes, bool) or nodes < 0:
            raise ValueError("nodes must be a non-negative integer")
        self._adj: list[set[int]] = [set() for _ in range(nodes)]
        self._edges = 0

    # -- helpers -----------------------------------------------------------

    def _check(self, u: int) -> None:
        if isinstance(u, bool) or not isinstance(u, int):
            raise IndexError(f"node id must be an int, got {u!r}")
        if not 0 <= u < len(self._adj):
            raise IndexError(f"node {u} out of range for graph with {len(self._adj)} nodes")

    # -- public API --------------------------------------------------------

    def add_edge(self, u: int, v: int) -> None:
        self._check(u)
        self._check(v)
        if v in self._adj[u]:
            return  # duplicate edge: no-op
        self._adj[u].add(v)
        self._adj[v].add(u)  # for u == v this is the same set; loop stored once
        self._edges += 1

    def remove_edge(self, u: int, v: int) -> bool:
        """Remove the edge ``u``–``v``. Returns True if an edge was removed."""
        self._check(u)
        self._check(v)
        if v not in self._adj[u]:
            return False
        self._adj[u].discard(v)
        self._adj[v].discard(u)  # same set when u == v; discard is idempotent
        self._edges -= 1
        return True

    def degree(self, u: int) -> int:
        """Number of distinct neighbours of ``u``; a self-loop counts once."""
        self._check(u)
        return len(self._adj[u])

    def has_edge(self, u: int, v: int) -> bool:
        self._check(u)
        self._check(v)
        return v in self._adj[u]

    def neighbors(self, u: int) -> list[int]:
        self._check(u)
        return sorted(self._adj[u])

    def edges(self) -> list[tuple[int, int]]:
        """Every edge once as ``(min, max)``, sorted."""
        return sorted((u, v) for u, nbrs in enumerate(self._adj) for v in nbrs if v >= u)

    def add_node(self) -> int:
        """Append a new isolated node and return its id."""
        self._adj.append(set())
        return len(self._adj) - 1

    def remove_node(self, u: int) -> None:
        """Delete ``u`` and its edges; every id above ``u`` shifts down by one."""
        self._check(u)
        self._edges -= len(self._adj[u])  # a self-loop appears once, so it is subtracted once
        del self._adj[u]
        for i, nbrs in enumerate(self._adj):
            self._adj[i] = {w - 1 if w > u else w for w in nbrs if w != u}

    def node_count(self) -> int:
        return len(self._adj)

    def edge_count(self) -> int:
        return self._edges

    def shortest_path(self, u: int, v: int) -> list[int] | None:
        self._check(u)
        self._check(v)
        if u == v:
            return [u]
        parent: dict[int, int] = {u: u}
        queue = deque([u])
        while queue:
            cur = queue.popleft()
            for nxt in self._adj[cur]:
                if nxt in parent:
                    continue
                parent[nxt] = cur
                if nxt == v:
                    path = [v]
                    while path[-1] != u:
                        path.append(parent[path[-1]])
                    path.reverse()
                    return path
                queue.append(nxt)
        return None

    def connected_components(self) -> list[list[int]]:
        """Return the connected components, each sorted, ordered by smallest node."""
        seen = [False] * len(self._adj)
        components: list[list[int]] = []
        for start in range(len(self._adj)):
            if seen[start]:
                continue
            seen[start] = True
            component = [start]
            stack = [start]
            while stack:
                cur = stack.pop()
                for nxt in self._adj[cur]:
                    if not seen[nxt]:
                        seen[nxt] = True
                        component.append(nxt)
                        stack.append(nxt)
            component.sort()
            components.append(component)
        return components

    def is_bipartite(self) -> bool:
        """True if the nodes can be 2-coloured so every edge joins different colours.

        A self-loop makes a graph non-bipartite.
        """
        color = [-1] * len(self._adj)
        for start in range(len(self._adj)):
            if color[start] != -1:
                continue
            color[start] = 0
            queue = deque([start])
            while queue:
                cur = queue.popleft()
                for nxt in self._adj[cur]:
                    if color[nxt] == -1:
                        color[nxt] = 1 - color[cur]
                        queue.append(nxt)
                    elif color[nxt] == color[cur]:
                        return False
        return True

    def subgraph(self, nodes: list[int]) -> Graph:
        """Induced subgraph on ``nodes``; ``nodes[i]`` becomes id ``i`` in the result."""
        for u in nodes:
            self._check(u)
        if len(set(nodes)) != len(nodes):
            raise ValueError("subgraph nodes must be distinct")
        new_id = {old: i for i, old in enumerate(nodes)}
        g = Graph(len(nodes))
        for old, i in new_id.items():
            for w in self._adj[old]:
                j = new_id.get(w)
                if j is not None and j >= i:
                    g.add_edge(i, j)
        return g

    def common_neighbors(self, u: int, v: int) -> list[int]:
        """Sorted nodes adjacent to both ``u`` and ``v``."""
        self._check(u)
        self._check(v)
        return sorted(self._adj[u] & self._adj[v])
