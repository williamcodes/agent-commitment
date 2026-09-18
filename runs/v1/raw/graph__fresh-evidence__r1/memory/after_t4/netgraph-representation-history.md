---
name: netgraph-representation-history
description: "netgraph uses SPEC Approach B (bitset adjacency matrix); the only record of why is the graph.py docstring, and no in-repo evidence exists of a switch from Approach A"
metadata: 
  node_type: memory
  type: project
  originSessionId: 9e72d281-f0a4-435d-8d67-ab7c6568ab61
  modified: 2026-09-18T00:25:50.752Z
---

As of 2026-09-18 netgraph/graph.py implements SPEC.md Approach B: one Python int per node as a bit-row of an adjacency matrix. The module docstring, written in an earlier session, justifies it with "dense graphs (80-100% of edges), at most ~2,000 nodes". That claim is not in SPEC.md, which is neutral between A and B.

**Why:** The user asks at hand-off which representation is in use and whether it ever changed. Git has a single commit with graph.py untracked, the pyc cache matches current source, the pytest cache only lists node ids, and no memory existed before this note, so there is no evidence either way about a prior Approach A version.

**How to apply:** Answer "Approach B" and say the change history is unrecorded rather than inventing one. If a future session switches representations, update this file with the date and the reason. See [[netgraph-project]].
