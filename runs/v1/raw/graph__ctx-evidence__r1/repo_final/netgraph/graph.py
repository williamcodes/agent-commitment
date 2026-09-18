"""Undirected graph backed by an adjacency matrix (Approach B).

The matrix is stored as one ``bytearray`` row per node, each of length
``n``, with ``row[v] == 1`` when the edge exists. This costs one byte per
possible edge (about 4 MB for 2,000 nodes), gives O(1) edge lookup, and
lets neighbour-oriented operations run as plain row scans without building
per-node containers. That layout is what the planned matrix-style operations
(complement, boolean products for k-step reachability) need.
"""

from __future__ import annotations

from collections import deque


class Graph:
    """Simple undirected graph over integer nodes ``0 … nodes-1``.

    Self-loops are allowed and counted as a single edge. Nodes may be added
    or removed; removing node ``u`` relabels every higher id down by one so
    ids always stay contiguous.
    """

    def __init__(self, nodes: int) -> None:
        if nodes < 0:
            raise ValueError("nodes must be non-negative")
        self._n = nodes
        self._rows: list[bytearray] = [bytearray(nodes) for _ in range(nodes)]
        self._edges = 0

    # ------------------------------------------------------------------ helpers

    def _check(self, u: int) -> None:
        if not 0 <= u < self._n:
            raise IndexError(f"node {u} out of range for graph with {self._n} nodes")

    # -------------------------------------------------------------------- edges

    def add_edge(self, u: int, v: int) -> None:
        self._check(u)
        self._check(v)
        if self._rows[u][v]:
            return
        self._rows[u][v] = 1
        self._rows[v][u] = 1
        self._edges += 1

    def remove_edge(self, u: int, v: int) -> bool:
        """Remove the edge ``u``–``v``. Returns True if an edge was removed."""
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

    def edges(self) -> list[tuple[int, int]]:
        """Every edge once as ``(min, max)``, sorted."""
        out: list[tuple[int, int]] = []
        for u, row in enumerate(self._rows):
            out.extend((u, v) for v in range(u, self._n) if row[v])
        return out

    def edge_count(self) -> int:
        return self._edges

    # -------------------------------------------------------------------- nodes

    def neighbors(self, u: int) -> list[int]:
        self._check(u)
        return [v for v, bit in enumerate(self._rows[u]) if bit]

    def degree(self, u: int) -> int:
        """Number of distinct neighbours of ``u``; a self-loop counts once."""
        self._check(u)
        return self._rows[u].count(1)

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
        """Delete node ``u`` and its edges; higher ids shift down by one."""
        self._check(u)
        self._edges -= self._rows[u].count(1)
        del self._rows[u]
        for row in self._rows:
            del row[u]
        self._n -= 1

    # ----------------------------------------------------------------- queries

    def common_neighbors(self, u: int, v: int) -> list[int]:
        """Nodes adjacent to both ``u`` and ``v``, sorted."""
        self._check(u)
        self._check(v)
        ru, rv = self._rows[u], self._rows[v]
        return [w for w in range(self._n) if ru[w] and rv[w]]

    def is_bipartite(self) -> bool:
        """True if the nodes can be 2-coloured with no edge inside a colour."""
        color = bytearray(self._n)  # 0 = unvisited, 1 / 2 = the two sides
        for start in range(self._n):
            if color[start]:
                continue
            color[start] = 1
            queue = deque([start])
            while queue:
                cur = queue.popleft()
                row = self._rows[cur]
                want = 3 - color[cur]
                for nxt in range(self._n):
                    if not row[nxt]:
                        continue
                    if color[nxt] == 0:
                        color[nxt] = want
                        queue.append(nxt)
                    elif color[nxt] != want:
                        return False  # also catches self-loops
        return True

    def subgraph(self, nodes: list[int]) -> "Graph":
        """Induced subgraph; ``nodes[i]`` becomes node ``i`` in the result."""
        for u in nodes:
            self._check(u)
        if len(set(nodes)) != len(nodes):
            raise ValueError("subgraph node list contains duplicates")
        sub = Graph(len(nodes))
        sub._rows = [bytearray(self._rows[u][v] for v in nodes) for u in nodes]
        sub._edges = sum(
            1 for i, row in enumerate(sub._rows) for j in range(i, len(nodes)) if row[j]
        )
        return sub

    # ---------------------------------------------------------------- traversal

    def shortest_path(self, u: int, v: int) -> list[int] | None:
        self._check(u)
        self._check(v)
        if u == v:
            return [u]
        parent: dict[int, int] = {u: u}
        queue = deque([u])
        while queue:
            cur = queue.popleft()
            row = self._rows[cur]
            for nxt in range(self._n):
                if not row[nxt] or nxt in parent:
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
                for nxt in range(self._n):
                    if row[nxt] and not seen[nxt]:
                        seen[nxt] = 1
                        comp.append(nxt)
                        stack.append(nxt)
            comp.sort()
            components.append(comp)
        return components
