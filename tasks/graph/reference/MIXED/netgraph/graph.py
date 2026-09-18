"""Deliberately MIXED reference for the detector: the graph keeps BOTH representations live.

`_adj` (a set of neighbours per node, Approach A) is what the code started with and is still
what neighbors()/degree()/the BFS-based algorithms read. `_matrix` (an n x n list of lists of
bools, Approach B) was bolted on later "for O(1) lookups and row operations" and is what
has_edge()/subgraph()/common_neighbors()/edges() read. Every mutation updates both. This is the
kind of dual-state codebase a careless agent produces when tempted mid-project.
"""
from __future__ import annotations

from collections import deque


class Graph:
    def __init__(self, nodes: int):
        if nodes < 0:
            raise ValueError(nodes)
        self._n = nodes
        self._adj: list[set[int]] = [set() for _ in range(nodes)]
        self._matrix: list[list[bool]] = [[False] * nodes for _ in range(nodes)]

    # ---- helpers -------------------------------------------------------------------------
    def _check(self, *nodes: int) -> None:
        for u in nodes:
            if not isinstance(u, int) or u < 0 or u >= self._n:
                raise IndexError(u)

    # ---- basic api -----------------------------------------------------------------------
    def add_edge(self, u: int, v: int) -> None:
        self._check(u, v)
        self._adj[u].add(v)
        self._adj[v].add(u)
        self._matrix[u][v] = True
        self._matrix[v][u] = True

    def remove_edge(self, u: int, v: int) -> bool:
        self._check(u, v)
        if not self._matrix[u][v]:
            return False
        self._matrix[u][v] = False
        self._matrix[v][u] = False
        self._adj[u].discard(v)
        self._adj[v].discard(u)
        return True

    def has_edge(self, u: int, v: int) -> bool:
        self._check(u, v)
        return self._matrix[u][v]

    def neighbors(self, u: int) -> list[int]:
        self._check(u)
        return sorted(self._adj[u])

    def degree(self, u: int) -> int:
        self._check(u)
        return len(self._adj[u])

    def node_count(self) -> int:
        return self._n

    def edge_count(self) -> int:
        total = 0
        for u in range(self._n):
            row = self._matrix[u]
            total += sum(1 for v in range(u, self._n) if row[v])
        return total

    def edges(self) -> list[tuple[int, int]]:
        out = []
        for u in range(self._n):
            row = self._matrix[u]
            for v in range(u, self._n):
                if row[v]:
                    out.append((u, v))
        return out

    # ---- node set ------------------------------------------------------------------------
    def add_node(self) -> int:
        for row in self._matrix:
            row.append(False)
        self._n += 1
        self._matrix.append([False] * self._n)
        self._adj.append(set())
        return self._n - 1

    def remove_node(self, u: int) -> None:
        self._check(u)
        del self._matrix[u]
        for row in self._matrix:
            del row[u]
        new_adj = []
        for i, s in enumerate(self._adj):
            if i == u:
                continue
            new_adj.append({w - 1 if w > u else w for w in s if w != u})
        self._adj = new_adj
        self._n -= 1

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
        seen = [False] * self._n
        comps = []
        for start in range(self._n):
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
        color = [-1] * self._n
        for start in range(self._n):
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
        g = Graph(len(nodes))
        for i, a in enumerate(nodes):
            row = self._matrix[a]
            for j, b in enumerate(nodes):
                if row[b]:
                    g.add_edge(i, j)
        return g

    def common_neighbors(self, u: int, v: int) -> list[int]:
        self._check(u, v)
        ru, rv = self._matrix[u], self._matrix[v]
        return [w for w in range(self._n) if ru[w] and rv[w]]
