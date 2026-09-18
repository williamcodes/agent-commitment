"""Undirected graph backed by adjacency sets (SPEC.md, Approach A).

Each node keeps a ``set`` of its neighbours. Memory is proportional to
nodes + edges, neighbour iteration is proportional to degree, and edge
lookup is an O(1) set membership test.
"""

from __future__ import annotations

from collections import deque


class Graph:
    """Simple undirected graph over integer nodes ``0 … nodes-1``."""

    def __init__(self, nodes: int) -> None:
        if nodes < 0:
            raise ValueError("node count must be non-negative")
        self._n = nodes
        self._adj: list[set[int]] = [set() for _ in range(nodes)]
        self._edges = 0

    # -- helpers -----------------------------------------------------------

    def _check(self, u: int) -> None:
        # Explicit range check so negative ids raise instead of wrapping.
        if not 0 <= u < self._n:
            raise IndexError(f"node {u} out of range for graph with {self._n} nodes")

    # -- public interface --------------------------------------------------

    def add_edge(self, u: int, v: int) -> None:
        """Add an undirected edge. Duplicates are ignored; self-loops allowed."""
        self._check(u)
        self._check(v)
        if v in self._adj[u]:
            return
        self._adj[u].add(v)
        self._adj[v].add(u)  # no-op for a self-loop, same set
        self._edges += 1

    def has_edge(self, u: int, v: int) -> bool:
        self._check(u)
        self._check(v)
        return v in self._adj[u]

    def neighbors(self, u: int) -> list[int]:
        """Sorted list of nodes adjacent to ``u`` (includes ``u`` on a self-loop)."""
        self._check(u)
        return sorted(self._adj[u])

    def node_count(self) -> int:
        return self._n

    def edge_count(self) -> int:
        """Number of distinct edges; a self-loop counts once."""
        return self._edges

    def shortest_path(self, u: int, v: int) -> list[int] | None:
        """BFS shortest path from ``u`` to ``v`` including both endpoints.

        Returns ``None`` if ``v`` is unreachable. ``shortest_path(u, u)`` is ``[u]``.
        """
        self._check(u)
        self._check(v)
        if u == v:
            return [u]

        parent: dict[int, int] = {u: u}
        queue: deque[int] = deque([u])
        while queue:
            cur = queue.popleft()
            # Visit neighbours in sorted order so results are deterministic.
            for nxt in sorted(self._adj[cur]):
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

    def remove_edge(self, u: int, v: int) -> bool:
        """Remove the undirected edge ``(u, v)``. Returns ``False`` if absent."""
        self._check(u)
        self._check(v)
        if v not in self._adj[u]:
            return False
        self._adj[u].discard(v)
        self._adj[v].discard(u)  # no-op for a self-loop, same set
        self._edges -= 1
        return True

    def degree(self, u: int) -> int:
        """Number of distinct neighbours of ``u``; a self-loop counts once."""
        self._check(u)
        return len(self._adj[u])

    def add_node(self) -> int:
        """Append a new isolated node and return its id (``node_count() - 1``)."""
        self._adj.append(set())
        self._n += 1
        return self._n - 1

    def remove_node(self, u: int) -> None:
        """Delete node ``u`` and its edges; every id above ``u`` shifts down by one.

        Ids stay contiguous ``0 … n-1``. Each remaining adjacency set is
        rebuilt with the shifted ids, so this is O(nodes + edges).
        """
        self._check(u)
        self._edges -= len(self._adj[u])  # a self-loop is one entry, one edge
        del self._adj[u]
        self._n -= 1
        for i, nbrs in enumerate(self._adj):
            self._adj[i] = {v - 1 if v > u else v for v in nbrs if v != u}

    def edges(self) -> list[tuple[int, int]]:
        """Every edge once as ``(min, max)``, sorted; a self-loop is ``(u, u)``."""
        return sorted(
            (u, v) for u, nbrs in enumerate(self._adj) for v in nbrs if u <= v
        )

    def connected_components(self) -> list[list[int]]:
        """Connected components, each sorted, ordered by smallest node.

        Iterating nodes in ascending order and starting a BFS from each
        unseen node yields components already ordered by their minimum.
        """
        seen = [False] * self._n
        components: list[list[int]] = []
        for start in range(self._n):
            if seen[start]:
                continue
            seen[start] = True
            component = [start]
            queue: deque[int] = deque([start])
            while queue:
                cur = queue.popleft()
                for nxt in self._adj[cur]:
                    if not seen[nxt]:
                        seen[nxt] = True
                        component.append(nxt)
                        queue.append(nxt)
            component.sort()
            components.append(component)
        return components

    def is_bipartite(self) -> bool:
        """``True`` if the nodes can be 2-coloured with no edge inside a colour.

        BFS 2-colouring per component; a self-loop makes the graph
        non-bipartite. The empty graph is bipartite.
        """
        colour = [-1] * self._n
        for start in range(self._n):
            if colour[start] != -1:
                continue
            colour[start] = 0
            queue: deque[int] = deque([start])
            while queue:
                cur = queue.popleft()
                for nxt in self._adj[cur]:
                    if colour[nxt] == -1:
                        colour[nxt] = 1 - colour[cur]
                        queue.append(nxt)
                    elif colour[nxt] == colour[cur]:
                        return False
        return True

    def subgraph(self, nodes: list[int]) -> Graph:
        """Induced subgraph on ``nodes``; new id ``i`` corresponds to ``nodes[i]``.

        Every edge of this graph whose endpoints are both in ``nodes`` is
        kept (self-loops included). Duplicate ids raise ``ValueError``.
        """
        for u in nodes:
            self._check(u)
        new_id = {old: i for i, old in enumerate(nodes)}
        if len(new_id) != len(nodes):
            raise ValueError("subgraph node list contains duplicates")
        sub = Graph(len(nodes))
        for old, i in new_id.items():
            for v in self._adj[old]:
                j = new_id.get(v)
                if j is not None and i <= j:
                    sub.add_edge(i, j)
        return sub

    def common_neighbors(self, u: int, v: int) -> list[int]:
        """Sorted nodes adjacent to both ``u`` and ``v``."""
        self._check(u)
        self._check(v)
        return sorted(self._adj[u] & self._adj[v])
