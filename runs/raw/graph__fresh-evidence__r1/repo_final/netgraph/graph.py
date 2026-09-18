"""Undirected graph backed by a bitset adjacency matrix (Approach B).

Representation
--------------
``self._rows[u]`` is a Python ``int`` used as a bitset: bit ``v`` is set iff
the edge ``u``–``v`` exists. The matrix is kept symmetric, and a self-loop
``u``–``u`` is bit ``u`` of row ``u``.

Why this representation:

* One bit per possible edge, so a 2,000-node graph is ~500 KB regardless of
  density (a ``set`` per node costs ~10x that at 80–100% density).
* Row operations are single big-int operations: ``a | b``, ``a & b``,
  ``~a & mask``. Complement graphs and boolean matrix products (k-step
  reachability) are built from exactly these, with no per-neighbour
  containers allocated.
* Edge lookup is O(1); adding a node is appending a ``0`` row (existing rows
  grow implicitly because ints are unbounded); removing a node is a
  shift-and-mask per row, which is how ids are relabelled.
"""

from __future__ import annotations


def _bits(row: int) -> list[int]:
    """Indices of the set bits of ``row``, ascending.

    ``bin(row)`` is MSB-first with a ``0b`` prefix; ``[:1:-1]`` reverses it
    and drops the prefix, so character ``i`` of the result is bit ``i``.
    """
    return [i for i, c in enumerate(bin(row)[:1:-1]) if c == "1"]


class Graph:
    """Simple undirected graph over integer nodes ``0 … nodes-1``."""

    def __init__(self, nodes: int) -> None:
        if nodes < 0:
            raise ValueError("nodes must be non-negative")
        self._rows: list[int] = [0] * nodes
        self._edge_count = 0

    # ---- helpers -------------------------------------------------------

    def _check(self, u: int) -> None:
        if not isinstance(u, int) or isinstance(u, bool):
            raise TypeError(f"node id must be an int, got {type(u).__name__}")
        if not 0 <= u < len(self._rows):
            raise IndexError(f"node {u} out of range for graph with {len(self._rows)} nodes")

    def _all_mask(self) -> int:
        """Bitset with every node's bit set."""
        return (1 << len(self._rows)) - 1

    # ---- nodes ---------------------------------------------------------

    def node_count(self) -> int:
        return len(self._rows)

    def add_node(self) -> int:
        """Append a new isolated node and return its id."""
        self._rows.append(0)
        return len(self._rows) - 1

    def remove_node(self, u: int) -> None:
        """Delete ``u`` and its edges; every id above ``u`` shifts down by one."""
        self._check(u)
        self._edge_count -= self._rows[u].bit_count()  # self-loop is one bit, counted once
        del self._rows[u]
        low = (1 << u) - 1
        # Drop bit u from each row: keep bits below u, shift bits above u down.
        self._rows = [(row >> (u + 1)) << u | (row & low) for row in self._rows]

    # ---- edges ---------------------------------------------------------

    def add_edge(self, u: int, v: int) -> None:
        self._check(u)
        self._check(v)
        if self._rows[u] >> v & 1:
            return  # duplicate edge: no-op
        self._rows[u] |= 1 << v
        self._rows[v] |= 1 << u  # for u == v this sets the same bit again
        self._edge_count += 1

    def remove_edge(self, u: int, v: int) -> bool:
        """Remove edge ``u``–``v``. Returns True if it existed, else False."""
        self._check(u)
        self._check(v)
        if not self._rows[u] >> v & 1:
            return False
        self._rows[u] &= ~(1 << v)
        self._rows[v] &= ~(1 << u)
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
        """Number of distinct neighbours of ``u``; a self-loop counts once."""
        self._check(u)
        return self._rows[u].bit_count()

    def common_neighbors(self, u: int, v: int) -> list[int]:
        """Nodes adjacent to both ``u`` and ``v``, sorted (row intersection)."""
        self._check(u)
        self._check(v)
        return _bits(self._rows[u] & self._rows[v])

    def edge_count(self) -> int:
        return self._edge_count

    def edges(self) -> list[tuple[int, int]]:
        """Every edge once as ``(min, max)``, sorted."""
        out: list[tuple[int, int]] = []
        for u, row in enumerate(self._rows):
            # Only bits >= u, so each edge appears once with u as the smaller end.
            out.extend((u, u + v) for v in _bits(row >> u))
        return out

    # ---- derived graphs ------------------------------------------------

    def subgraph(self, nodes: list[int]) -> Graph:
        """Induced subgraph on ``nodes``; new id ``i`` is old id ``nodes[i]``."""
        for u in nodes:
            self._check(u)
        sub = Graph(len(nodes))
        for i, u in enumerate(nodes):
            row = self._rows[u]
            # Gather the bits of old row ``u`` at old ids ``nodes[j]`` into bit ``j``.
            new_row = 0
            for j, v in enumerate(nodes):
                new_row |= (row >> v & 1) << j
            sub._rows[i] = new_row
        # Each edge sets two bits, except a self-loop which sets one.
        bits = sum(row.bit_count() for row in sub._rows)
        loops = sum(row >> i & 1 for i, row in enumerate(sub._rows))
        sub._edge_count = (bits + loops) // 2
        return sub

    # ---- traversal -----------------------------------------------------

    def connected_components(self) -> list[list[int]]:
        """Components as sorted node lists, ordered by their smallest node."""
        components: list[list[int]] = []
        unvisited = self._all_mask()
        while unvisited:
            comp = unvisited & -unvisited  # lowest unvisited node, as a bitset
            frontier = comp
            while frontier:
                reached = 0
                for j in _bits(frontier):
                    reached |= self._rows[j]
                frontier = reached & ~comp
                comp |= frontier
            unvisited &= ~comp
            components.append(_bits(comp))
        return components

    def is_bipartite(self) -> bool:
        """True iff the nodes can be 2-coloured with no edge inside a colour.

        Bitset BFS: each layer is the union of the previous layer's rows minus
        everything already coloured; a layer touching itself (which includes
        any self-loop) is an odd cycle.
        """
        colour = [0, 0]  # colour[c] is the bitset of nodes with colour c
        unvisited = self._all_mask()
        while unvisited:
            frontier = unvisited & -unvisited  # lowest uncoloured node
            c = 0
            while frontier:
                colour[c] |= frontier
                reached = 0
                for j in _bits(frontier):
                    reached |= self._rows[j]
                if reached & colour[c]:
                    return False  # an edge joins two nodes of the same colour
                c ^= 1
                frontier = reached & ~colour[c]
            unvisited &= ~(colour[0] | colour[1])
        return True

    def shortest_path(self, u: int, v: int) -> list[int] | None:
        self._check(u)
        self._check(v)
        if u == v:
            return [u]
        parent: dict[int, int] = {u: u}
        visited = 1 << u
        frontier = visited
        while frontier and v not in parent:
            next_frontier = 0
            for j in _bits(frontier):
                fresh = self._rows[j] & ~visited
                for k in _bits(fresh):
                    parent[k] = j
                visited |= fresh
                next_frontier |= fresh
            frontier = next_frontier
        if v not in parent:
            return None
        path = [v]
        while path[-1] != u:
            path.append(parent[path[-1]])
        path.reverse()
        return path
