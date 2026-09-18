"""Undirected graph stored as adjacency sets (Approach A): one set of neighbours per node."""
from __future__ import annotations

from collections import deque


class Graph:
    def __init__(self, nodes: int):
        if nodes < 0:
            raise ValueError(nodes)
        self._adj: list[set[int]] = [set() for _ in range(nodes)]

    # ---- helpers -------------------------------------------------------------------------
    def _check(self, *nodes: int) -> None:
        n = len(self._adj)
        for u in nodes:
            if not isinstance(u, int) or u < 0 or u >= n:
                raise IndexError(u)

    # ---- basic api -----------------------------------------------------------------------
    def add_edge(self, u: int, v: int) -> None:
        self._check(u, v)
        self._adj[u].add(v)
        self._adj[v].add(u)

    def remove_edge(self, u: int, v: int) -> bool:
        self._check(u, v)
        if v not in self._adj[u]:
            return False
        self._adj[u].discard(v)
        self._adj[v].discard(u)
        return True

    def has_edge(self, u: int, v: int) -> bool:
        self._check(u, v)
        return v in self._adj[u]

    def neighbors(self, u: int) -> list[int]:
        self._check(u)
        return sorted(self._adj[u])

    def degree(self, u: int) -> int:
        self._check(u)
        return len(self._adj[u])

    def node_count(self) -> int:
        return len(self._adj)

    def edge_count(self) -> int:
        total = 0
        for u, s in enumerate(self._adj):
            total += len(s) + (1 if u in s else 0)
        return total // 2

    def edges(self) -> list[tuple[int, int]]:
        out = []
        for u, s in enumerate(self._adj):
            for v in s:
                if u <= v:
                    out.append((u, v))
        out.sort()
        return out

    # ---- node set ------------------------------------------------------------------------
    def add_node(self) -> int:
        self._adj.append(set())
        return len(self._adj) - 1

    def remove_node(self, u: int) -> None:
        self._check(u)
        new_adj = []
        for i, s in enumerate(self._adj):
            if i == u:
                continue
            new_adj.append({w - 1 if w > u else w for w in s if w != u})
        self._adj = new_adj

    # ---- algorithms ----------------------------------------------------------------------
    def shortest_path(self, u: int, v: int) -> list[int] | None:
        self._check(u, v)
        if u == v:
            return [u]
        prev = {u: None}
        q = deque([u])
        while q:
            x = q.popleft()
            for y in self._adj[x]:
                if y not in prev:
                    prev[y] = x
                    if y == v:
                        path = [v]
                        while prev[path[-1]] is not None:
                            path.append(prev[path[-1]])
                        return path[::-1]
                    q.append(y)
        return None

    def connected_components(self) -> list[list[int]]:
        seen = [False] * len(self._adj)
        comps = []
        for start in range(len(self._adj)):
            if seen[start]:
                continue
            seen[start] = True
            comp = [start]
            q = deque([start])
            while q:
                x = q.popleft()
                for y in self._adj[x]:
                    if not seen[y]:
                        seen[y] = True
                        comp.append(y)
                        q.append(y)
            comps.append(sorted(comp))
        comps.sort(key=lambda c: c[0])
        return comps

    def is_bipartite(self) -> bool:
        color = [-1] * len(self._adj)
        for start in range(len(self._adj)):
            if color[start] != -1:
                continue
            color[start] = 0
            q = deque([start])
            while q:
                x = q.popleft()
                for y in self._adj[x]:
                    if color[y] == -1:
                        color[y] = 1 - color[x]
                        q.append(y)
                    elif color[y] == color[x]:
                        return False
        return True

    def subgraph(self, nodes: list[int]) -> "Graph":
        self._check(*nodes)
        index = {old: new for new, old in enumerate(nodes)}
        g = Graph(len(nodes))
        for old, new in index.items():
            for w in self._adj[old]:
                if w in index:
                    g._adj[new].add(index[w])
        return g

    def common_neighbors(self, u: int, v: int) -> list[int]:
        self._check(u, v)
        return sorted(self._adj[u] & self._adj[v])
