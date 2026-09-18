"""Undirected graph backed by adjacency sets (Approach A from SPEC.md).

Each node keeps a set of its neighbours, so memory is proportional to
nodes + edges and neighbour iteration is proportional to degree.
"""

from __future__ import annotations

from collections import deque


class Graph:
    """A simple undirected graph over integer nodes ``0 … nodes-1``."""

    def __init__(self, nodes: int):
        if nodes < 0:
            raise ValueError("nodes must be non-negative")
        self._n = nodes
        self._adj: list[set[int]] = [set() for _ in range(nodes)]
        self._edges = 0

    def _check(self, u: int) -> None:
        if not 0 <= u < self._n:
            raise IndexError(f"node {u} out of range for graph with {self._n} nodes")

    def add_edge(self, u: int, v: int) -> None:
        """Add an undirected edge. Duplicates are ignored; self-loops allowed."""
        self._check(u)
        self._check(v)
        if v in self._adj[u]:
            return
        self._adj[u].add(v)
        self._adj[v].add(u)
        self._edges += 1

    def has_edge(self, u: int, v: int) -> bool:
        self._check(u)
        self._check(v)
        return v in self._adj[u]

    def remove_edge(self, u: int, v: int) -> bool:
        """Remove the edge ``u``–``v``. Return ``True`` if it existed."""
        self._check(u)
        self._check(v)
        if v not in self._adj[u]:
            return False
        self._adj[u].discard(v)
        self._adj[v].discard(u)
        self._edges -= 1
        return True

    def degree(self, u: int) -> int:
        """Number of distinct neighbours of ``u`` (a self-loop counts once)."""
        self._check(u)
        return len(self._adj[u])

    def add_node(self) -> int:
        """Append a new isolated node and return its id (``node_count() - 1``)."""
        self._adj.append(set())
        self._n += 1
        return self._n - 1

    def remove_node(self, u: int) -> None:
        """Delete node ``u`` and every edge incident to it.

        Every node with an id greater than ``u`` is relabelled down by one so
        that ids stay contiguous in ``0 … n-1``.
        """
        self._check(u)
        self._edges -= len(self._adj[u])
        del self._adj[u]
        self._n -= 1
        for i, nbrs in enumerate(self._adj):
            nbrs.discard(u)
            self._adj[i] = {v - 1 if v > u else v for v in nbrs}

    def edges(self) -> list[tuple[int, int]]:
        """Return every edge once as ``(min, max)``, sorted."""
        return sorted(
            (u, v) for u, nbrs in enumerate(self._adj) for v in nbrs if u <= v
        )

    def neighbors(self, u: int) -> list[int]:
        self._check(u)
        return sorted(self._adj[u])

    def node_count(self) -> int:
        return self._n

    def edge_count(self) -> int:
        return self._edges

    def shortest_path(self, u: int, v: int) -> list[int] | None:
        """Return a shortest path from ``u`` to ``v`` (inclusive) via BFS.

        Returns ``None`` if ``v`` is unreachable from ``u``. Neighbours are
        expanded in ascending order so results are deterministic.
        """
        self._check(u)
        self._check(v)
        if u == v:
            return [u]
        parent: dict[int, int] = {u: u}
        queue: deque[int] = deque([u])
        while queue:
            cur = queue.popleft()
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

    def connected_components(self) -> list[list[int]]:
        """Return the connected components, each sorted, ordered by smallest node."""
        seen = [False] * self._n
        comps: list[list[int]] = []
        for start in range(self._n):
            if seen[start]:
                continue
            seen[start] = True
            comp = [start]
            queue: deque[int] = deque([start])
            while queue:
                cur = queue.popleft()
                for nxt in self._adj[cur]:
                    if not seen[nxt]:
                        seen[nxt] = True
                        comp.append(nxt)
                        queue.append(nxt)
            comp.sort()
            comps.append(comp)
        return comps

    def is_bipartite(self) -> bool:
        """Return ``True`` if the nodes can be 2-coloured with no monochromatic edge.

        Every component is BFS-coloured independently. A self-loop makes the
        graph non-bipartite. The empty graph is bipartite.
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
        """Return the subgraph induced by ``nodes``.

        The new graph has ``len(nodes)`` nodes; ``nodes[i]`` becomes id ``i``.
        Every edge (including self-loops) whose endpoints are both in
        ``nodes`` is kept. Duplicate ids raise ``ValueError``.
        """
        for u in nodes:
            self._check(u)
        if len(set(nodes)) != len(nodes):
            raise ValueError("subgraph nodes must be distinct")
        new_id = {old: new for new, old in enumerate(nodes)}
        sub = Graph(len(nodes))
        for old_u, u in new_id.items():
            for old_v in self._adj[old_u]:
                v = new_id.get(old_v)
                if v is not None and u <= v:
                    sub.add_edge(u, v)
        return sub

    def common_neighbors(self, u: int, v: int) -> list[int]:
        """Return the sorted list of nodes adjacent to both ``u`` and ``v``."""
        self._check(u)
        self._check(v)
        return sorted(self._adj[u] & self._adj[v])
