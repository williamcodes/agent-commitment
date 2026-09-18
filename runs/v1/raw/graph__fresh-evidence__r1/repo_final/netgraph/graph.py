"""Undirected graph backed by a bitset adjacency matrix (SPEC.md, Approach B).

Row ``u`` of the matrix is a Python ``int`` whose bit ``v`` is set iff the
edge ``u -- v`` exists; the matrix is kept symmetric.  A self-loop is bit
``u`` of row ``u``.

Why a bitset matrix:

* Graphs are dense (80-100% of possible edges) with at most ~2,000 nodes, so
  memory is ~n*n/8 bytes (about 0.5 MB at n = 2,000) instead of one hashed
  int per edge endpoint.
* Row-wise operations are single big-int instructions that run in C and
  never allocate per-neighbour containers: complement is ``row ^ mask``,
  the union of several rows is ``|``, a boolean matrix product row is the
  OR of the rows selected by the bits of another row.
* Adding a node appends a zero row; removing node ``u`` deletes its row and
  splices bit ``u`` out of every other row, which is O(n) row operations.
"""

from __future__ import annotations

from collections.abc import Iterator


def _bits(mask: int) -> Iterator[int]:
    """Yield the positions of the set bits of ``mask`` in ascending order."""
    while mask:
        low = mask & -mask
        yield low.bit_length() - 1
        mask ^= low


class Graph:
    """Simple undirected graph over integer nodes ``0 … nodes-1``."""

    def __init__(self, nodes: int) -> None:
        if nodes < 0:
            raise ValueError("node count must be non-negative")
        self._rows: list[int] = [0] * nodes
        self._edges = 0

    # -- helpers ---------------------------------------------------------

    def _check(self, u: int) -> None:
        if not isinstance(u, int) or isinstance(u, bool):
            raise TypeError(f"node id must be an int, got {type(u).__name__}")
        if not 0 <= u < len(self._rows):
            raise IndexError(f"node {u} out of range for graph with {len(self._rows)} nodes")

    def _reach(self, frontier: int) -> int:
        """Union of the rows of every node in the ``frontier`` bitset."""
        rows = self._rows
        reach = 0
        for w in _bits(frontier):
            reach |= rows[w]
        return reach

    # -- public interface ------------------------------------------------

    def add_edge(self, u: int, v: int) -> None:
        self._check(u)
        self._check(v)
        if self._rows[u] >> v & 1:
            return  # already present; matrix is symmetric
        self._rows[u] |= 1 << v
        self._rows[v] |= 1 << u  # same bit for self-loops
        self._edges += 1

    def has_edge(self, u: int, v: int) -> bool:
        self._check(u)
        self._check(v)
        return bool(self._rows[u] >> v & 1)

    def neighbors(self, u: int) -> list[int]:
        self._check(u)
        return list(_bits(self._rows[u]))

    def node_count(self) -> int:
        return len(self._rows)

    def edge_count(self) -> int:
        return self._edges

    def shortest_path(self, u: int, v: int) -> list[int] | None:
        self._check(u)
        self._check(v)
        if u == v:
            return [u]
        # Level-synchronous BFS on bitsets: ``levels[i]`` is the set of nodes
        # at distance exactly i from ``u``.
        visited = frontier = 1 << u
        levels = [frontier]
        while not visited >> v & 1:
            frontier = self._reach(frontier) & ~visited
            if not frontier:
                return None
            visited |= frontier
            levels.append(frontier)
        # Walk back from ``v``: each node has a neighbour one level closer.
        path = [v]
        for level in reversed(levels[:-1]):
            path.append(next(_bits(level & self._rows[path[-1]])))
        path.reverse()
        return path

    def remove_edge(self, u: int, v: int) -> bool:
        """Remove the edge ``u -- v``; return ``True`` if it was present."""
        self._check(u)
        self._check(v)
        if not self._rows[u] >> v & 1:
            return False
        self._rows[u] &= ~(1 << v)
        self._rows[v] &= ~(1 << u)  # same bit for self-loops
        self._edges -= 1
        return True

    def degree(self, u: int) -> int:
        """Number of distinct neighbours of ``u``; a self-loop counts once."""
        self._check(u)
        return self._rows[u].bit_count()

    def connected_components(self) -> list[list[int]]:
        """Components as sorted node lists, ordered by their smallest node."""
        unseen = (1 << len(self._rows)) - 1
        components: list[list[int]] = []
        while unseen:
            component = frontier = unseen & -unseen  # lowest unseen node
            while frontier:
                frontier = self._reach(frontier) & ~component
                component |= frontier
            components.append(list(_bits(component)))
            unseen &= ~component
        return components

    def add_node(self) -> int:
        """Append a new isolated node and return its id."""
        self._rows.append(0)
        return len(self._rows) - 1

    def remove_node(self, u: int) -> None:
        """Delete node ``u`` and its edges; every higher id shifts down by one."""
        self._check(u)
        rows = self._rows
        self._edges -= rows[u].bit_count()  # incident edges, self-loop once
        del rows[u]
        low = (1 << u) - 1
        for i, row in enumerate(rows):
            rows[i] = (row & low) | (row >> (u + 1)) << u

    def edges(self) -> list[tuple[int, int]]:
        """Every edge once as ``(min, max)``, in sorted order."""
        out: list[tuple[int, int]] = []
        for u, row in enumerate(self._rows):
            out.extend((u, u + offset) for offset in _bits(row >> u))
        return out

    def is_bipartite(self) -> bool:
        """``True`` iff the nodes can be 2-coloured with no monochrome edge.

        Level-synchronous BFS per component: nodes at the same distance from
        the start get the same colour, so the graph is bipartite iff no edge
        joins two nodes of the same BFS level.  A self-loop puts a node in
        its own level's neighbourhood and is therefore rejected too.
        """
        unseen = (1 << len(self._rows)) - 1
        while unseen:
            frontier = unseen & -unseen  # lowest unseen node starts a component
            unseen ^= frontier
            while frontier:
                reach = self._reach(frontier)
                if reach & frontier:
                    return False
                frontier = reach & unseen
                unseen &= ~frontier
        return True

    def subgraph(self, nodes: list[int]) -> Graph:
        """Induced subgraph on ``nodes``; new id ``i`` is old id ``nodes[i]``."""
        for u in nodes:
            self._check(u)
        if len(set(nodes)) != len(nodes):
            raise ValueError("subgraph nodes must be distinct")
        new_id = {u: i for i, u in enumerate(nodes)}
        selected = 0
        for u in nodes:
            selected |= 1 << u
        sub = Graph(len(nodes))
        for i, u in enumerate(nodes):
            row = 0
            for w in _bits(self._rows[u] & selected):
                row |= 1 << new_id[w]
            sub._rows[i] = row
        # Each edge once: count the bits on or above the diagonal.
        sub._edges = sum((row >> i).bit_count() for i, row in enumerate(sub._rows))
        return sub

    def common_neighbors(self, u: int, v: int) -> list[int]:
        """Nodes adjacent to both ``u`` and ``v``, sorted ascending."""
        self._check(u)
        self._check(v)
        return list(_bits(self._rows[u] & self._rows[v]))
