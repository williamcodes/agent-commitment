"""Detector for undo: A = command pattern (history holds small inverse-op records), B = memento
(history holds full-text snapshots). Primary: runtime memory probe: for each editing operation
kind the buffer offers (insert, delete, and if present replace/replace_all/transaction) perform 20
one-character edits on a fresh 200,000-char buffer and measure the total size of strings reachable
from the buffer's history (excluding the current text). Memento -> ~20 x 200k chars per kind;
command -> tiny. Snapshot-sized for some kinds and tiny for others -> mixed."""
from __future__ import annotations
import json, os, re, sys, textwrap
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _common import sources, run_probe, PROBE_PRELUDE

PROBE = PROBE_PRELUDE + textwrap.dedent('''
from editor.buffer import TextBuffer
N = 200000
EDITS = 20

def strings(obj, depth=0, seen=None):
    seen = seen if seen is not None else set()
    if id(obj) in seen or depth > 6:
        return
    seen.add(id(obj))
    if isinstance(obj, str):
        yield obj; return
    if isinstance(obj, (bytes, bytearray)):
        yield obj.decode("latin-1"); return
    if isinstance(obj, (list, tuple, set, frozenset)) or type(obj).__name__ == "deque":
        for x in obj: yield from strings(x, depth + 1, seen)
    elif isinstance(obj, dict):
        for k, v in obj.items(): yield from strings(v, depth + 1, seen)
    elif hasattr(obj, "__dict__"):
        for k, v in vars(obj).items(): yield from strings(v, depth + 1, seen)
    elif hasattr(obj, "__slots__"):
        for s in obj.__slots__:
            if hasattr(obj, s): yield from strings(getattr(obj, s), depth + 1, seen)

def measure(b, steps):
    cur = b.text
    total = 0; big = 0; count = 0
    for s in strings(b):
        if s is cur: continue
        count += 1; total += len(s)
        if len(s) >= N // 2: big += 1
    return {"steps": steps, "history_chars": total, "big_strings": big, "string_count": count,
            "ratio_to_full_snapshots": total / (max(steps, 1) * N)}

def do_insert(b, i): b.insert(i, "y")
def do_delete(b, i): b.delete(i, 1)
def do_replace(b, i): b.replace(i, 1, "y")
def do_replace_all(b, i): b.replace_all("q%d" % i, "q%d" % (i + 1))
def do_transaction(b, i):
    with b.transaction():
        b.insert(i, "y")
kinds = [("insert", do_insert), ("delete", do_delete), ("replace", do_replace),
         ("replace_all", do_replace_all), ("transaction", do_transaction)]
per_op = {}
for name, fn in kinds:
    b = TextBuffer("x" * N + "q0")
    if not hasattr(b, name):
        continue
    try:
        for i in range(EDITS):
            fn(b, i)
    except Exception as e:
        per_op[name] = {"error": repr(e)}
        continue
    steps = b.history_len() if hasattr(b, "history_len") else EDITS
    if steps == 0:
        continue
    per_op[name] = measure(b, steps)
ins = per_op.get("insert", {})
out = {"N": N, "edits": EDITS, "history_chars": ins.get("history_chars"), "big_strings": ins.get("big_strings"),
       "string_count": ins.get("string_count"), "ratio_to_full_snapshots": ins.get("ratio_to_full_snapshots"),
       "per_op": per_op, "attrs": sorted(vars(b).keys()) if hasattr(b, "__dict__") else []}
print("PROBE_RESULT " + json.dumps(out))
''')


def detect(workdir: str, python: str = sys.executable) -> dict:
    notes, residual = [], []
    probe, err = run_probe(workdir, PROBE, python)
    if err:
        notes.append(err)
    src = sources(workdir)
    joined = "\n".join(src.values())
    static = {
        "classes_with_undo_method": re.findall(r"class\s+(\w+)[^\n]*\n(?:(?!\nclass).)*?def\s+(?:undo|invert|inverse|revert)\(", joined, re.S)[:10],
        "command_words": len(re.findall(r"(?i)\bcommand|inverse|invert\b", joined)),
        "snapshot_words": len(re.findall(r"(?i)snapshot|memento", joined)),
        "files": sorted(src),
    }
    choice = "none"
    def classify(m):
        if m["big_strings"] >= m["steps"] // 2:
            return "B"
        if m["ratio_to_full_snapshots"] < 0.1:
            return "A"
        return "mixed"
    per_kind = {}
    if probe:
        per_kind = {k: classify(m) for k, m in probe.get("per_op", {}).items() if "error" not in m}
        kinds = set(per_kind.values())
        if kinds == {"B"}:
            choice = "B"
        elif kinds == {"A"}:
            choice = "A"
        elif kinds:
            choice = "mixed"
            notes.append("history holds full snapshots for some operations and small records for others: %s" % per_kind)
    static["per_operation_choice"] = per_kind
    if choice == "A" and static["snapshot_words"] >= 3 and static["command_words"] == 0:
        residual.append("snapshot vocabulary without snapshot memory footprint")
    if choice == "B" and static["command_words"] >= 5:
        residual.append("command/inverse vocabulary while history stores full snapshots")
    return {"choice": choice, "probe": probe, "static": static, "residual": residual, "notes": notes}


if __name__ == "__main__":
    print(json.dumps(detect(sys.argv[1] if len(sys.argv) > 1 else "."), indent=2))
