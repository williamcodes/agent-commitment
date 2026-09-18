"""Undirected graph backed by adjacency sets (Approach A).

Nodes are integers ``0 … n-1``. Each node maps to the set of its neighbours,
so memory is proportional to nodes + edges and neighbour iteration is
proportional to degree.
"""

from __future__ import annotations

from collections import deque


class Graph:
    def __init__(self, nodes: int):
        if nodes < 0:
            raise ValueError("node count must be non-negative")
        self._n = nodes
        self._adj: list[set[int]] = [set() for _ in range(nodes)]
        self._edges = 0

    def _check(self, u: int) -> None:
        if not 0 <= u < self._n:
            raise IndexError(f"node {u} out of range for graph with {self._n} nodes")

    def add_edge(self, u: int, v: int) -> None:
        self._check(u)
        self._check(v)
        if v in self._adj[u]:
            return
        self._adj[u].add(v)
        self._adj[v].add(u)  # no-op for self-loops (same set)
        self._edges += 1

    def has_edge(self, u: int, v: int) -> bool:
        self._check(u)
        self._check(v)
        return v in self._adj[u]

    def neighbors(self, u: int) -> list[int]:
        self._check(u)
        return sorted(self._adj[u])

    def node_count(self) -> int:
        return self._n

    def edge_count(self) -> int:
        return self._edges

    def remove_edge(self, u: int, v: int) -> bool:
        """Remove the edge u–v. Returns True if it existed, False otherwise."""
        self._check(u)
        self._check(v)
        if v not in self._adj[u]:
            return False
        self._adj[u].discard(v)
        self._adj[v].discard(u)  # no-op for self-loops (same set)
        self._edges -= 1
        return True

    def degree(self, u: int) -> int:
        """Number of distinct neighbours of u; a self-loop counts once."""
        self._check(u)
        return len(self._adj[u])

    def connected_components(self) -> list[list[int]]:
        """Components as sorted node lists, ordered by their smallest node."""
        seen = [False] * self._n
        comps: list[list[int]] = []
        for start in range(self._n):
            if seen[start]:
                continue
            seen[start] = True
            comp = [start]
            stack = [start]
            while stack:
                x = stack.pop()
                for y in self._adj[x]:
                    if not seen[y]:
                        seen[y] = True
                        comp.append(y)
                        stack.append(y)
            comp.sort()
            comps.append(comp)
        return comps

    def add_node(self) -> int:
        """Append a new isolated node and return its id."""
        self._adj.append(set())
        self._n += 1
        return self._n - 1

    def remove_node(self, u: int) -> None:
        """Delete node u and its edges; every id above u shifts down by one."""
        self._check(u)
        self._edges -= len(self._adj[u])
        del self._adj[u]
        self._n -= 1
        for i, nbrs in enumerate(self._adj):
            if u in nbrs or any(y > u for y in nbrs):
                self._adj[i] = {y - 1 if y > u else y for y in nbrs if y != u}

    def edges(self) -> list[tuple[int, int]]:
        """Every edge once as (min, max), sorted."""
        return sorted(
            (x, y) for x, nbrs in enumerate(self._adj) for y in nbrs if y >= x
        )

    def is_bipartite(self) -> bool:
        """True if the nodes can be 2-coloured with no edge inside a colour."""
        colour = [-1] * self._n
        for start in range(self._n):
            if colour[start] != -1:
                continue
            colour[start] = 0
            queue = deque([start])
            while queue:
                x = queue.popleft()
                for y in self._adj[x]:
                    if colour[y] == -1:
                        colour[y] = 1 - colour[x]
                        queue.append(y)
                    elif colour[y] == colour[x]:  # also catches self-loops
                        return False
        return True

    def subgraph(self, nodes: list[int]) -> Graph:
        """Induced subgraph; nodes[i] becomes id i in the result."""
        for u in nodes:
            self._check(u)
        new_id = {u: i for i, u in enumerate(nodes)}
        if len(new_id) != len(nodes):
            raise ValueError("subgraph node list contains duplicates")
        sub = Graph(len(nodes))
        for u, i in new_id.items():
            for y in self._adj[u]:
                j = new_id.get(y)
                if j is not None and j >= i:
                    sub.add_edge(i, j)
        return sub

    def common_neighbors(self, u: int, v: int) -> list[int]:
        """Sorted nodes adjacent to both u and v."""
        self._check(u)
        self._check(v)
        return sorted(self._adj[u] & self._adj[v])

    def shortest_path(self, u: int, v: int) -> list[int] | None:
        self._check(u)
        self._check(v)
        if u == v:
            return [u]
        parent: dict[int, int] = {u: u}
        queue = deque([u])
        while queue:
            x = queue.popleft()
            for y in self._adj[x]:
                if y in parent:
                    continue
                parent[y] = x
                if y == v:
                    path = [v]
                    while path[-1] != u:
                        path.append(parent[path[-1]])
                    path.reverse()
                    return path
                queue.append(y)
        return None
