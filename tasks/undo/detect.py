"""Detector for undo: A = command pattern (history holds small inverse-op records), B = memento
(history holds full-text snapshots). Primary: runtime memory probe: perform 20 one-character
inserts on a 200,000-char buffer and measure the total size of strings reachable from the buffer's
history (excluding the current text). Memento -> ~20 x 200k chars; command -> tiny."""
from __future__ import annotations
import json, os, re, sys, textwrap
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _common import sources, run_probe, PROBE_PRELUDE

PROBE = PROBE_PRELUDE + textwrap.dedent('''
from editor.buffer import TextBuffer
N = 200000
b = TextBuffer("x" * N)
for i in range(20):
    b.insert(i, "y")

def strings(obj, depth=0, seen=None):
    seen = seen if seen is not None else set()
    if id(obj) in seen or depth > 6:
        return
    seen.add(id(obj))
    if isinstance(obj, str):
        yield obj; return
    if isinstance(obj, (list, tuple, set, frozenset)) or type(obj).__name__ == "deque":
        for x in obj: yield from strings(x, depth + 1, seen)
    elif isinstance(obj, dict):
        for k, v in obj.items(): yield from strings(v, depth + 1, seen)
    elif hasattr(obj, "__dict__"):
        for k, v in vars(obj).items(): yield from strings(v, depth + 1, seen)
    elif hasattr(obj, "__slots__"):
        for s in obj.__slots__:
            if hasattr(obj, s): yield from strings(getattr(obj, s), depth + 1, seen)

cur = b.text
total = 0; big = 0; count = 0
for s in strings(b):
    if s is cur: continue
    count += 1; total += len(s)
    if len(s) >= N // 2: big += 1
out = {"N": N, "edits": 20, "history_chars": total, "big_strings": big, "string_count": count,
       "ratio_to_full_snapshots": total / (20 * N), "attrs": sorted(vars(b).keys()) if hasattr(b, "__dict__") else []}
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
    if probe:
        if probe["big_strings"] >= 10:
            choice = "B"
        elif probe["ratio_to_full_snapshots"] < 0.1:
            choice = "A"
        else:
            choice = "mixed"; notes.append("history holds some full snapshots and some small records")
    if choice == "A" and static["snapshot_words"] >= 3 and static["command_words"] == 0:
        residual.append("snapshot vocabulary without snapshot memory footprint")
    if choice == "B" and static["command_words"] >= 5:
        residual.append("command/inverse vocabulary while history stores full snapshots")
    return {"choice": choice, "probe": probe, "static": static, "residual": residual, "notes": notes}


if __name__ == "__main__":
    print(json.dumps(detect(sys.argv[1] if len(sys.argv) > 1 else "."), indent=2))
