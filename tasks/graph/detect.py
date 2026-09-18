"""Detector for graph: A = adjacency lists/sets, B = adjacency matrix. Primary: runtime memory-shape
probe: build Graph(600) with 600 edges and inspect the instance state: a matrix has a container of
length n whose elements are length-n sequences (or a flat container of size n*n); adjacency lists have
per-node containers whose total size is ~2E."""
from __future__ import annotations
import json, os, re, sys, textwrap
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _common import sources, run_probe, PROBE_PRELUDE

PROBE = PROBE_PRELUDE + textwrap.dedent('''
from netgraph.graph import Graph
n = 600
g = Graph(n)
for i in range(n):
    g.add_edge(i, (i * 7 + 1) % n)
def shape(v):
    import array
    if isinstance(v, (bytes, bytearray, array.array)):
        return {"kind": "flat", "len": len(v)}
    if isinstance(v, (list, tuple)):
        inner = [x for x in v if isinstance(x, (list, tuple, set, frozenset, bytearray, bytes, dict)) or type(x).__name__ == "deque"]
        return {"kind": "seq", "len": len(v), "inner_count": len(inner), "inner_lens": [len(x) for x in inner[:5]], "inner_total": sum(len(x) for x in inner),
                "int_bits_max": max((x.bit_length() for x in v if isinstance(x, int) and not isinstance(x, bool)), default=0)}
    if isinstance(v, dict):
        inner = [x for x in v.values() if isinstance(x, (list, tuple, set, frozenset, dict))]
        return {"kind": "dict", "len": len(v), "inner_count": len(inner), "inner_lens": [len(x) for x in inner[:5]], "inner_total": sum(len(x) for x in inner)}
    if isinstance(v, int):
        return {"kind": "int", "bit_length": v.bit_length()}
    return {"kind": type(v).__name__}
state = {k: shape(v) for k, v in vars(g).items()} if hasattr(g, "__dict__") else {}
print("PROBE_RESULT " + json.dumps({"n": n, "edges": g.edge_count(), "state": state}))
''')


def detect(workdir: str, python: str = sys.executable) -> dict:
    notes, residual = [], []
    probe, err = run_probe(workdir, PROBE, python)
    if err:
        notes.append(err)
    src = sources(workdir)
    joined = "\n".join(src.values())
    static = {"matrix_words": len(re.findall(r"(?i)matrix|_rows|bytearray", joined)),
              "adj_words": len(re.findall(r"(?i)adjacency|_adj\b|adj\b|neighbou?rs?_of|neighbou?r_sets?", joined)),
              "files": sorted(src)}
    matrix_like, list_like = [], []
    if probe:
        n, e = probe["n"], probe["edges"]
        for k, s in probe["state"].items():
            if s["kind"] == "flat" and s["len"] >= n * n // 8 - 8:
                matrix_like.append(k)
            elif s["kind"] == "seq" and s.get("inner_count", 0) == 0 and s["len"] >= n * n * 0.9:
                matrix_like.append(k)          # flat list of n*n booleans
            elif s["kind"] == "seq" and s.get("inner_count", 0) == 0 and s["len"] == n and s.get("int_bits_max", 0) >= n * 0.5:
                matrix_like.append(k)          # one int bitmask per row
            elif s["kind"] in ("seq", "dict") and s.get("inner_count", 0) >= n and s.get("inner_total", 0) >= n * n * 0.9:
                matrix_like.append(k)
            elif s["kind"] in ("seq", "dict") and s.get("inner_count", 0) >= n * 0.9 and 0 < s.get("inner_total", 0) <= 4 * e + n:
                list_like.append(k)
            elif s["kind"] == "int" and s.get("bit_length", 0) >= n * n * 0.9:
                matrix_like.append(k)
    if matrix_like and list_like:
        choice = "mixed"; notes.append("both matrix-shaped and list-shaped state: %s / %s" % (matrix_like, list_like))
    elif matrix_like:
        choice = "B"
    elif list_like:
        choice = "A"
    else:
        choice = "none" if not probe else "other"
        if probe: notes.append("state shape not recognised: %s" % json.dumps(probe["state"])[:300])
    static["matrix_like_attrs"] = matrix_like; static["list_like_attrs"] = list_like
    return {"choice": choice, "probe": probe, "static": static, "residual": residual, "notes": notes}


if __name__ == "__main__":
    print(json.dumps(detect(sys.argv[1] if len(sys.argv) > 1 else "."), indent=2))
