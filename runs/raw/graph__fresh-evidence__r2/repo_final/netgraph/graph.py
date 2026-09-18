"""Undirected graph backed by a bitset adjacency matrix (Approach B in SPEC.md).

Row ``u`` of the matrix is a single Python ``int``; bit ``v`` is set when the
edge ``u-v`` exists.  The graphs this library targets are dense (80-100% of
all possible edges) with at most a few thousand nodes, so an n x n matrix is
both the compact choice (n**2 / 8 bytes: 0.5 MB at n = 2000, versus hundreds
of megabytes for adjacency sets) and the fast one for the matrix-style
operations that follow (complement, boolean products, k-step reachability).
Those become one big-int operation per row -- ``~row & mask``, ``row_a |
row_b`` -- with no per-neighbour containers allocated.
"""

from __future__ import annotations


def _bits(row: int) -> list[int]:
    """Positions of the set bits of ``row`` in ascending order.

    Scanning the binary string is ~4x faster than a ``row & -row`` loop on
    the dense rows this library targets, because each big-int op costs
    O(n/64) words while the string scan is a single C-level conversion.
    """
    return [i for i, c in enumerate(f"{row:b}"[::-1]) if c == "1"]


class Graph:
    """Undirected graph over integer nodes 0 ... nodes-1."""

    def __init__(self, nodes: int) -> None:
        if nodes < 0:
            raise ValueError("node count must be non-negative")
        self._rows: list[int] = [0] * nodes
        self._edge_count = 0

    # -- helpers -----------------------------------------------------------

    def _check(self, u: int) -> None:
        if not 0 <= u < len(self._rows):
            raise IndexError(f"node {u} out of range for graph with {len(self._rows)} nodes")

    # -- nodes -------------------------------------------------------------

    def node_count(self) -> int:
        return len(self._rows)

    def add_node(self) -> int:
        """Append an isolated node and return its id."""
        self._rows.append(0)
        return len(self._rows) - 1

    def remove_node(self, u: int) -> None:
        """Delete node ``u`` and its edges; every higher id shifts down by one."""
        self._check(u)
        self._edge_count -= self._rows[u].bit_count()  # a self-loop is one bit
        del self._rows[u]
        low = (1 << u) - 1  # bits strictly below u stay put
        # Keep bits < u, drop bit u, shift bits > u down by one.
        self._rows = [(r & low) | ((r >> 1) & ~low) for r in self._rows]

    # -- edges -------------------------------------------------------------

    def add_edge(self, u: int, v: int) -> None:
        self._check(u)
        self._check(v)
        bit = 1 << v
        row = self._rows[u]
        if row & bit:
            return
        self._rows[u] = row | bit
        self._rows[v] |= 1 << u  # no-op for self-loops (same row, same bit)
        self._edge_count += 1

    def remove_edge(self, u: int, v: int) -> bool:
        """Remove the edge u-v. Return True if it existed, False otherwise."""
        self._check(u)
        self._check(v)
        if not self._rows[u] >> v & 1:
            return False
        self._rows[u] &= ~(1 << v)
        self._rows[v] &= ~(1 << u)  # no-op for self-loops
        self._edge_count -= 1
        return True

    def has_edge(self, u: int, v: int) -> bool:
        self._check(u)
        self._check(v)
        return bool(self._rows[u] >> v & 1)

    def neighbors(self, u: int) -> list[int]:
        self._check(u)
        return _bits(self._rows[u])

    def degree(self, u: int) -> int:
        """Number of distinct neighbours of u; a self-loop counts once."""
        self._check(u)
        return self._rows[u].bit_count()

    def edge_count(self) -> int:
        return self._edge_count

    def edges(self) -> list[tuple[int, int]]:
        """Every edge once as ``(min, max)``, in sorted order."""
        out: list[tuple[int, int]] = []
        for u, row in enumerate(self._rows):
            # Bits at or above u: shift so bit 0 is node u itself.
            out.extend((u, u + off) for off in _bits(row >> u))
        return out

    def common_neighbors(self, u: int, v: int) -> list[int]:
        """Nodes adjacent to both u and v, in ascending order."""
        self._check(u)
        self._check(v)
        return _bits(self._rows[u] & self._rows[v])

    # -- traversal ---------------------------------------------------------

    def shortest_path(self, u: int, v: int) -> list[int] | None:
        self._check(u)
        self._check(v)
        if u == v:
            return [u]
        target = 1 << v
        parent: dict[int, int] = {u: u}
        visited = frontier = 1 << u
        while frontier and not visited & target:
            next_frontier = 0
            for cur in _bits(frontier):
                new = self._rows[cur] & ~visited
                if not new:
                    continue
                for nxt in _bits(new):
                    parent[nxt] = cur
                visited |= new
                next_frontier |= new
            frontier = next_frontier
        if not visited & target:
            return None
        path = [v]
        while path[-1] != u:
            path.append(parent[path[-1]])
        path.reverse()
        return path

    def connected_components(self) -> list[list[int]]:
        """Connected components, each sorted, ordered by their smallest node."""
        remaining = (1 << len(self._rows)) - 1
        components: list[list[int]] = []
        while remaining:
            start = (remaining & -remaining).bit_length() - 1  # lowest unseen node
            component = frontier = 1 << start
            while frontier:
                reach = 0
                for cur in _bits(frontier):
                    reach |= self._rows[cur]
                frontier = reach & ~component
                component |= frontier
            components.append(_bits(component))
            remaining &= ~component
        return components

    def is_bipartite(self) -> bool:
        """True if the nodes can be 2-coloured so that no edge joins equal colours.

        A BFS from each unseen node assigns colours by level parity, so the
        graph is bipartite exactly when no edge joins two nodes of the same
        BFS level.  A self-loop is such an edge, so it makes the graph
        non-bipartite.
        """
        remaining = (1 << len(self._rows)) - 1
        while remaining:
            start = (remaining & -remaining).bit_length() - 1
            visited = frontier = 1 << start
            while frontier:
                reach = 0
                for cur in _bits(frontier):
                    reach |= self._rows[cur]
                if reach & frontier:  # edge inside one level
                    return False
                frontier = reach & ~visited
                visited |= frontier
            remaining &= ~visited
        return True

    # -- derived graphs ----------------------------------------------------

    def subgraph(self, nodes: list[int]) -> Graph:
        """Induced subgraph on ``nodes``; new id ``i`` is old node ``nodes[i]``."""
        for u in nodes:
            self._check(u)
        if len(set(nodes)) != len(nodes):
            raise ValueError("subgraph nodes must be distinct")
        sub = Graph(len(nodes))
        for i, u in enumerate(nodes):
            row = self._rows[u]
            sub._rows[i] = sum(1 << j for j, w in enumerate(nodes) if row >> w & 1)
        # Count each edge once: bits at or above the diagonal (self-loops included).
        sub._edge_count = sum((r >> i).bit_count() for i, r in enumerate(sub._rows))
        return sub
