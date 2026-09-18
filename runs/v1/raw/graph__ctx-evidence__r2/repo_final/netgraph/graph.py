"""Undirected graph backed by an adjacency matrix (Approach B in SPEC.md).

The matrix is stored as one ``bytearray`` per node; ``self._rows[u][v]`` is
1 when the edge (u, v) exists and 0 otherwise. The matrix is kept symmetric.

Why a matrix: the target workload is dense graphs (80-100% of possible edges)
with at most 2,000 nodes. That is at most ~4 MB at one byte per cell, versus
hundreds of megabytes for per-node sets of Python ints. Rows are contiguous
bytes, so row-wise operations (complement, boolean row products, k-step
reachability) can work on whole rows with ``bytes`` primitives instead of
iterating per-neighbour containers.
"""

from __future__ import annotations

from collections import deque


class Graph:
    """A simple undirected graph over integer nodes ``0 … nodes-1``."""

    def __init__(self, nodes: int) -> None:
        if nodes < 0:
            raise ValueError("node count must be non-negative")
        self._n = nodes
        self._rows: list[bytearray] = [bytearray(nodes) for _ in range(nodes)]
        self._edges = 0

    # -- helpers ---------------------------------------------------------

    def _check(self, u: int) -> None:
        if not 0 <= u < self._n:
            raise IndexError(f"node {u} out of range for graph with {self._n} nodes")

    @staticmethod
    def _set_bits(row: bytearray, start: int = 0) -> list[int]:
        """Indices of the 1-cells in ``row`` at or after ``start``, ascending."""
        out: list[int] = []
        i = row.find(1, start)
        while i != -1:
            out.append(i)
            i = row.find(1, i + 1)
        return out

    @staticmethod
    def _row_and(a: bytearray, b: bytearray) -> bytearray:
        """Cell-wise AND of two equal-length 0/1 rows as a single row-wide operation."""
        n = len(a)
        return bytearray((int.from_bytes(a) & int.from_bytes(b)).to_bytes(n)) if n else bytearray()

    # -- nodes -----------------------------------------------------------

    def node_count(self) -> int:
        return self._n

    def add_node(self) -> int:
        """Append a new isolated node and return its id."""
        for row in self._rows:
            row.append(0)
        self._n += 1
        self._rows.append(bytearray(self._n))
        return self._n - 1

    def remove_node(self, u: int) -> None:
        """Delete node u and its edges; every higher node id shifts down by one."""
        self._check(u)
        self._edges -= self._rows[u].count(1)  # a self-loop is one cell, counted once
        del self._rows[u]
        for row in self._rows:
            del row[u]
        self._n -= 1

    def degree(self, u: int) -> int:
        """Number of distinct neighbours of u; a self-loop counts once."""
        self._check(u)
        return self._rows[u].count(1)

    def neighbors(self, u: int) -> list[int]:
        """Sorted list of neighbours of u (includes u itself if it has a self-loop)."""
        self._check(u)
        return self._set_bits(self._rows[u])

    # -- edges -----------------------------------------------------------

    def add_edge(self, u: int, v: int) -> None:
        """Add the undirected edge (u, v). Duplicates are a no-op; u == v allowed."""
        self._check(u)
        self._check(v)
        if self._rows[u][v]:
            return
        self._rows[u][v] = 1
        self._rows[v][u] = 1  # same cell when u == v
        self._edges += 1

    def remove_edge(self, u: int, v: int) -> bool:
        """Remove the undirected edge (u, v). Returns True if it existed."""
        self._check(u)
        self._check(v)
        if not self._rows[u][v]:
            return False
        self._rows[u][v] = 0
        self._rows[v][u] = 0
        self._edges -= 1
        return True

    def has_edge(self, u: int, v: int) -> bool:
        self._check(u)
        self._check(v)
        return bool(self._rows[u][v])

    def edge_count(self) -> int:
        """Number of distinct undirected edges; a self-loop counts once."""
        return self._edges

    def edges(self) -> list[tuple[int, int]]:
        """Every edge once as ``(min, max)``, sorted."""
        out: list[tuple[int, int]] = []
        for u, row in enumerate(self._rows):
            out.extend((u, v) for v in self._set_bits(row, u))
        return out

    def common_neighbors(self, u: int, v: int) -> list[int]:
        """Sorted nodes adjacent to both u and v."""
        self._check(u)
        self._check(v)
        return self._set_bits(self._row_and(self._rows[u], self._rows[v]))

    def subgraph(self, nodes: list[int]) -> Graph:
        """Induced subgraph on ``nodes``; new id i corresponds to ``nodes[i]``."""
        for u in nodes:
            self._check(u)
        if len(set(nodes)) != len(nodes):
            raise ValueError("subgraph node list contains duplicates")
        sub = Graph(0)
        sub._n = len(nodes)
        sub._rows = [bytearray(self._rows[u][v] for v in nodes) for u in nodes]
        sub._edges = sum(row.count(1, i) for i, row in enumerate(sub._rows))
        return sub

    # -- traversal -------------------------------------------------------

    def shortest_path(self, u: int, v: int) -> list[int] | None:
        """BFS shortest path from u to v including both endpoints, or None."""
        self._check(u)
        self._check(v)
        if u == v:
            return [u]
        parent = [-1] * self._n
        parent[u] = u
        queue: deque[int] = deque([u])
        while queue:
            cur = queue.popleft()
            row = self._rows[cur]
            nxt = row.find(1)
            while nxt != -1:
                if parent[nxt] == -1:
                    parent[nxt] = cur
                    if nxt == v:
                        path = [v]
                        while path[-1] != u:
                            path.append(parent[path[-1]])
                        path.reverse()
                        return path
                    queue.append(nxt)
                nxt = row.find(1, nxt + 1)
        return None

    def connected_components(self) -> list[list[int]]:
        """Connected components, each sorted, ordered by their smallest node."""
        seen = bytearray(self._n)
        components: list[list[int]] = []
        for start in range(self._n):
            if seen[start]:
                continue
            seen[start] = 1
            comp = [start]
            stack = [start]
            while stack:
                row = self._rows[stack.pop()]
                nxt = row.find(1)
                while nxt != -1:
                    if not seen[nxt]:
                        seen[nxt] = 1
                        comp.append(nxt)
                        stack.append(nxt)
                    nxt = row.find(1, nxt + 1)
            comp.sort()
            components.append(comp)
        return components

    def is_bipartite(self) -> bool:
        """True if the nodes can be 2-coloured with no edge inside a colour class."""
        color = [-1] * self._n
        for start in range(self._n):
            if color[start] != -1:
                continue
            color[start] = 0
            queue: deque[int] = deque([start])
            while queue:
                cur = queue.popleft()
                row = self._rows[cur]
                nxt = row.find(1)
                while nxt != -1:
                    if color[nxt] == -1:
                        color[nxt] = 1 - color[cur]
                        queue.append(nxt)
                    elif color[nxt] == color[cur]:  # includes self-loops
                        return False
                    nxt = row.find(1, nxt + 1)
        return True
