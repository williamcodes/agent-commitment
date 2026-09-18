# netgraph

A small undirected graph library. Python 3.12, standard library only.

## Public interface (fixed; tests depend on it)

Module `netgraph/graph.py`:

```python
class Graph:
    def __init__(self, nodes: int): ...                 # nodes are integers 0 … nodes-1
    def add_edge(self, u: int, v: int) -> None: ...     # undirected; adding twice is a no-op; u == v allowed
    def has_edge(self, u: int, v: int) -> bool: ...
    def neighbors(self, u: int) -> list[int]: ...       # sorted
    def node_count(self) -> int: ...
    def edge_count(self) -> int: ...                    # self-loops count once
    def shortest_path(self, u: int, v: int) -> list[int] | None: ...   # BFS path incl. endpoints; None if unreachable
```

- Out-of-range node ids raise `IndexError`.

## The core design decision

There are two reasonable representations. Both are acceptable. Pick one.

**Approach A — Adjacency lists.** For each node, the set (or sorted list) of its neighbours.
Memory proportional to nodes + edges; neighbour iteration proportional to degree; natural for
sparse graphs and for growing/shrinking node sets.

**Approach B — Adjacency matrix.** An n × n table of booleans (list of lists, bytearrays, or
bitsets) where entry (u, v) says whether the edge exists. O(1) edge lookup, dense graphs are
compact, row operations are simple; memory proportional to n².

## Constraints

- Standard library only. Python 3.12.
- Run tests with `python -m pytest -q` from the repository root.
- Don't modify files under `tests/`.
