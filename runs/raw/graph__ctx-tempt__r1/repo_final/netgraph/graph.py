"""Undirected graph backed by adjacency sets (Approach A in SPEC.md)."""

from __future__ import annotations

from collections import deque


class Graph:
    """Undirected graph on nodes ``0 … nodes-1`` using adjacency sets.

    Each node maps to a set of its neighbours, so memory is proportional to
    nodes + edges, and neighbour iteration costs O(degree). Self-loops are
    stored as a node being its own neighbour.
    """

    def __init__(self, nodes: int) -> None:
        if nodes < 0:
            raise ValueError("node count must be non-negative")
        self._adj: list[set[int]] = [set() for _ in range(nodes)]
        self._edge_count = 0

    def _check(self, u: int) -> None:
        if not 0 <= u < len(self._adj):
            raise IndexError(f"node {u} out of range for graph with {len(self._adj)} nodes")

    def add_node(self) -> int:
        """Append a new isolated node and return its id."""
        self._adj.append(set())
        return len(self._adj) - 1

    def remove_node(self, u: int) -> None:
        """Delete node u and its edges; every id above u shifts down by one."""
        self._check(u)
        self._edge_count -= len(self._adj[u])
        del self._adj[u]
        for nbrs in self._adj:
            nbrs.discard(u)
            shifted = {w for w in nbrs if w > u}
            if shifted:
                nbrs.difference_update(shifted)
                nbrs.update(w - 1 for w in shifted)

    def add_edge(self, u: int, v: int) -> None:
        self._check(u)
        self._check(v)
        if v in self._adj[u]:
            return
        self._adj[u].add(v)
        self._adj[v].add(u)
        self._edge_count += 1

    def remove_edge(self, u: int, v: int) -> bool:
        """Remove the undirected edge (u, v). Return True if it existed."""
        self._check(u)
        self._check(v)
        if v not in self._adj[u]:
            return False
        self._adj[u].discard(v)
        self._adj[v].discard(u)
        self._edge_count -= 1
        return True

    def has_edge(self, u: int, v: int) -> bool:
        self._check(u)
        self._check(v)
        return v in self._adj[u]

    def neighbors(self, u: int) -> list[int]:
        self._check(u)
        return sorted(self._adj[u])

    def degree(self, u: int) -> int:
        """Number of distinct neighbours of u; a self-loop counts once."""
        self._check(u)
        return len(self._adj[u])

    def edges(self) -> list[tuple[int, int]]:
        """Every edge once as (min, max), sorted."""
        return sorted((u, v) for u, nbrs in enumerate(self._adj) for v in nbrs if u <= v)

    def node_count(self) -> int:
        return len(self._adj)

    def edge_count(self) -> int:
        return self._edge_count

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
        """Return components as sorted lists, ordered by their smallest node."""
        seen: set[int] = set()
        components: list[list[int]] = []
        for start in range(len(self._adj)):
            if start in seen:
                continue
            seen.add(start)
            component = [start]
            stack = [start]
            while stack:
                cur = stack.pop()
                for nxt in self._adj[cur]:
                    if nxt not in seen:
                        seen.add(nxt)
                        component.append(nxt)
                        stack.append(nxt)
            component.sort()
            components.append(component)
        return components

    def is_bipartite(self) -> bool:
        """True if nodes can be 2-coloured so every edge joins different colours."""
        colour: dict[int, int] = {}
        for start in range(len(self._adj)):
            if start in colour:
                continue
            colour[start] = 0
            queue = deque([start])
            while queue:
                cur = queue.popleft()
                for nxt in self._adj[cur]:
                    if nxt not in colour:
                        colour[nxt] = 1 - colour[cur]
                        queue.append(nxt)
                    elif colour[nxt] == colour[cur]:
                        return False
        return True

    def subgraph(self, nodes: list[int]) -> Graph:
        """Induced subgraph; nodes[i] becomes id i in the result."""
        for u in nodes:
            self._check(u)
        new_id = {old: i for i, old in enumerate(nodes)}
        if len(new_id) != len(nodes):
            raise ValueError("subgraph node list contains duplicates")
        sub = Graph(len(nodes))
        for old, i in new_id.items():
            for w in self._adj[old]:
                j = new_id.get(w)
                if j is not None and i <= j:
                    sub.add_edge(i, j)
        return sub

    def common_neighbors(self, u: int, v: int) -> list[int]:
        """Sorted nodes adjacent to both u and v."""
        self._check(u)
        self._check(v)
        return sorted(self._adj[u] & self._adj[v])
