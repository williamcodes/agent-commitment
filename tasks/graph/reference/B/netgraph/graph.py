"""Undirected graph stored as an n x n adjacency matrix (Approach B): one bytearray row per node."""
from __future__ import annotations

from collections import deque


class Graph:
    def __init__(self, nodes: int):
        if nodes < 0:
            raise ValueError(nodes)
        self._n = nodes
        self._rows: list[bytearray] = [bytearray(nodes) for _ in range(nodes)]

    # ---- helpers -------------------------------------------------------------------------
    def _check(self, *nodes: int) -> None:
        for u in nodes:
            if not isinstance(u, int) or u < 0 or u >= self._n:
                raise IndexError(u)

    # ---- basic api -----------------------------------------------------------------------
    def add_edge(self, u: int, v: int) -> None:
        self._check(u, v)
        self._rows[u][v] = 1
        self._rows[v][u] = 1

    def remove_edge(self, u: int, v: int) -> bool:
        self._check(u, v)
        if not self._rows[u][v]:
            return False
        self._rows[u][v] = 0
        self._rows[v][u] = 0
        return True

    def has_edge(self, u: int, v: int) -> bool:
        self._check(u, v)
        return bool(self._rows[u][v])

    def neighbors(self, u: int) -> list[int]:
        self._check(u)
        row = self._rows[u]
        return [v for v in range(self._n) if row[v]]

    def degree(self, u: int) -> int:
        self._check(u)
        return sum(self._rows[u])

    def node_count(self) -> int:
        return self._n

    def edge_count(self) -> int:
        total = 0
        for u in range(self._n):
            total += sum(self._rows[u][u:])
        return total

    def edges(self) -> list[tuple[int, int]]:
        out = []
        for u in range(self._n):
            row = self._rows[u]
            for v in range(u, self._n):
                if row[v]:
                    out.append((u, v))
        return out

    # ---- node set ------------------------------------------------------------------------
    def add_node(self) -> int:
        for row in self._rows:
            row.append(0)
        self._n += 1
        self._rows.append(bytearray(self._n))
        return self._n - 1

    def remove_node(self, u: int) -> None:
        self._check(u)
        del self._rows[u]
        for row in self._rows:
            del row[u]
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
            row = self._rows[x]
            for y in range(self._n):
                if row[y] and y not in prev:
                    prev[y] = x
                    if y == v:
                        path = [v]
                        while prev[path[-1]] is not None:
                            path.append(prev[path[-1]])
                        return path[::-1]
                    q.append(y)
        return None

    def connected_components(self) -> list[list[int]]:
        seen = bytearray(self._n)
        comps = []
        for start in range(self._n):
            if seen[start]:
                continue
            seen[start] = 1
            comp = [start]
            q = deque([start])
            while q:
                x = q.popleft()
                row = self._rows[x]
                for y in range(self._n):
                    if row[y] and not seen[y]:
                        seen[y] = 1
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
                row = self._rows[x]
                for y in range(self._n):
                    if not row[y]:
                        continue
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
            row = self._rows[a]
            for j, b in enumerate(nodes):
                if row[b]:
                    g._rows[i][j] = 1
        return g

    def common_neighbors(self, u: int, v: int) -> list[int]:
        self._check(u, v)
        ru, rv = self._rows[u], self._rows[v]
        return [w for w in range(self._n) if ru[w] and rv[w]]
