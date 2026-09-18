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
    def remove_edge(self, u: int, v: int) -> bool: ...  # True if the edge existed
    def degree(self, u: int) -> int: ...                # distinct neighbours; a self-loop counts once
    def connected_components(self) -> list[list[int]]: ...  # each sorted, ordered by smallest node
    def add_node(self) -> int: ...                      # appends an isolated node, returns its id
    def remove_node(self, u: int) -> None: ...          # deletes u and its edges; higher ids shift down by one
    def edges(self) -> list[tuple[int, int]]: ...       # every edge once as (min, max), sorted
    def is_bipartite(self) -> bool: ...                 # 2-colourable; a self-loop makes it False
    def subgraph(self, nodes: list[int]) -> Graph: ...  # induced subgraph; new id i is old nodes[i]
    def common_neighbors(self, u: int, v: int) -> list[int]: ...  # sorted
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

**Decision: Approach B, one Python-int bitset per row** (`netgraph/graph.py`). The product
owner has confirmed the target graphs are dense (typically 80-100% of all possible edges) with at
most 2,000 nodes, and the next step adds matrix-style operations (complement, boolean matrix
products for k-step reachability) that must be row-wise and must not allocate per-neighbour
containers. Bitset rows cost n²/8 bytes (0.5 MB at n = 2000; adjacency sets measured 326 MB
on the same graph) and make each row operation a single big-int `&`, `|`, `~`.

## Constraints

- Standard library only. Python 3.12.
- Run tests with `python -m pytest -q` from the repository root.
- Don't modify files under `tests/`.
