"""Undirected graph backed by adjacency sets (Approach A in SPEC.md)."""

from __future__ import annotations

from collections import deque


class Graph:
    """Simple undirected graph over integer nodes ``0 … nodes-1``.

    Representation: one ``set`` of neighbour ids per node. Memory is
    proportional to nodes + edges, and neighbour iteration costs O(degree),
    which suits the sparse graphs this library is aimed at.
    """

    def __init__(self, nodes: int) -> None:
        if nodes < 0:
            raise ValueError("nodes must be non-negative")
        self._adj: list[set[int]] = [set() for _ in range(nodes)]
        self._edge_count = 0

    # -- helpers -----------------------------------------------------------

    def _check(self, u: int) -> None:
        if not 0 <= u < len(self._adj):
            raise IndexError(f"node {u} out of range for graph with {len(self._adj)} nodes")

    # -- public interface --------------------------------------------------

    def add_edge(self, u: int, v: int) -> None:
        self._check(u)
        self._check(v)
        if v in self._adj[u]:
            return  # duplicate edge is a no-op
        self._adj[u].add(v)
        self._adj[v].add(u)  # for u == v this is the same set; the loop counts once
        self._edge_count += 1

    def remove_edge(self, u: int, v: int) -> bool:
        """Remove the edge ``u``-``v``. Return ``True`` if it existed."""
        self._check(u)
        self._check(v)
        if v not in self._adj[u]:
            return False
        self._adj[u].discard(v)
        self._adj[v].discard(u)  # for u == v this is the same set; discard is idempotent
        self._edge_count -= 1
        return True

    def add_node(self) -> int:
        """Append a new isolated node and return its id (``node_count() - 1``)."""
        self._adj.append(set())
        return len(self._adj) - 1

    def remove_node(self, u: int) -> None:
        """Delete node ``u`` and its edges; every id above ``u`` shifts down by one.

        Ids therefore stay contiguous ``0 … n-1``. Costs O(nodes + edges) because
        every remaining adjacency set is rebuilt with relabelled ids.
        """
        self._check(u)
        self._edge_count -= len(self._adj[u])  # a self-loop is one entry, one edge
        for v in self._adj[u]:
            if v != u:
                self._adj[v].discard(u)
        del self._adj[u]
        self._adj = [{w - 1 if w > u else w for w in nbrs} for nbrs in self._adj]

    def edges(self) -> list[tuple[int, int]]:
        """Every edge once as ``(min, max)``, sorted; a self-loop appears as ``(u, u)``."""
        return sorted((u, v) for u, nbrs in enumerate(self._adj) for v in nbrs if v >= u)

    def has_edge(self, u: int, v: int) -> bool:
        self._check(u)
        self._check(v)
        return v in self._adj[u]

    def neighbors(self, u: int) -> list[int]:
        self._check(u)
        return sorted(self._adj[u])

    def degree(self, u: int) -> int:
        """Number of distinct neighbours of ``u``; a self-loop counts once."""
        self._check(u)
        return len(self._adj[u])

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
        queue: deque[int] = deque([u])
        while queue:
            cur = queue.popleft()
            for nxt in sorted(self._adj[cur]):
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
        """Return the connected components, each sorted, ordered by smallest node.

        Nodes are visited in increasing order, so each component is discovered
        from its smallest node and the result is naturally ordered.
        """
        seen = [False] * len(self._adj)
        components: list[list[int]] = []
        for start in range(len(self._adj)):
            if seen[start]:
                continue
            seen[start] = True
            component = [start]
            stack = [start]
            while stack:
                cur = stack.pop()
                for nxt in self._adj[cur]:
                    if not seen[nxt]:
                        seen[nxt] = True
                        component.append(nxt)
                        stack.append(nxt)
            component.sort()
            components.append(component)
        return components

    def is_bipartite(self) -> bool:
        """Return ``True`` if the nodes can be 2-coloured with no monochrome edge.

        BFS 2-colouring per component. A self-loop makes the graph
        non-bipartite. The empty graph is bipartite.
        """
        colour: list[int] = [-1] * len(self._adj)
        for start in range(len(self._adj)):
            if colour[start] != -1:
                continue
            colour[start] = 0
            queue: deque[int] = deque([start])
            while queue:
                cur = queue.popleft()
                for nxt in self._adj[cur]:
                    if colour[nxt] == -1:
                        colour[nxt] = 1 - colour[cur]
                        queue.append(nxt)
                    elif colour[nxt] == colour[cur]:
                        return False  # also catches self-loops
        return True

    def subgraph(self, nodes: list[int]) -> Graph:
        """Induced subgraph on ``nodes``; ``nodes[i]`` becomes id ``i`` in the result.

        Raises ``IndexError`` for out-of-range ids and ``ValueError`` if an id
        is listed more than once.
        """
        for u in nodes:
            self._check(u)
        if len(set(nodes)) != len(nodes):
            raise ValueError("subgraph node list contains duplicates")
        new_id = {old: new for new, old in enumerate(nodes)}
        sub = Graph(len(nodes))
        for old_u, u in new_id.items():
            for old_v in self._adj[old_u]:
                v = new_id.get(old_v)
                if v is not None and v >= u:  # each undirected edge once; keeps self-loops
                    sub.add_edge(u, v)
        return sub

    def common_neighbors(self, u: int, v: int) -> list[int]:
        """Sorted ids adjacent to both ``u`` and ``v``."""
        self._check(u)
        self._check(v)
        return sorted(self._adj[u] & self._adj[v])
