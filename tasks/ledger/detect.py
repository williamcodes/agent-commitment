"""Detector for ledger: A = event-sourced (append-only operation log is the source of truth),
B = snapshot state (balances mutated in place, no operation log).

Primary signal: runtime probe on the object's internal state. We perform N operations and check
whether some list/tuple-like container inside the Ledger instance grows by one entry per operation
(an operation log). Secondary: static name signals (event/replay/apply/fold) and in-place
augmented assignment on balances."""
from __future__ import annotations
import json, os, re, sys, textwrap
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _common import sources, run_probe, parse_all, PROBE_PRELUDE

PROBE = PROBE_PRELUDE + textwrap.dedent('''
from ledger.ledger import Ledger

def containers(obj, depth=0, seen=None):
    """Yield (path, container) for list/tuple/deque-like attributes reachable within 3 levels."""
    seen = seen if seen is not None else set()
    if id(obj) in seen or depth > 3:
        return
    seen.add(id(obj))
    items = []
    if hasattr(obj, "__dict__"):
        items = list(vars(obj).items())
    elif isinstance(obj, dict):
        items = list(obj.items())
    for k, v in items:
        if isinstance(v, (list, tuple, dict)) or type(v).__name__ == "deque":
            yield (str(k), v)
        if isinstance(v, (dict, list)) or hasattr(v, "__dict__"):
            if isinstance(v, list):
                for i, x in enumerate(v[:3]):
                    yield from containers(x, depth + 1, seen)
            else:
                yield from containers(v, depth + 1, seen)

def sizes(l):
    return {p: len(c) for p, c in containers(l)}

def dict_snapshots(l):
    return {p: repr(sorted(c.items(), key=repr)) for p, c in containers(l) if isinstance(c, dict)}

l = Ledger()
l.open_account("x", 100)
l.open_account("y", 0)
before = sizes(l)
dicts_before = dict_snapshots(l)
ops = 0
for i in range(10):
    l.deposit("x", 1); ops += 1
    l.withdraw("x", 1); ops += 1
    l.transfer("x", "y", 1); ops += 1
after = sizes(l)
dicts_after = dict_snapshots(l)
mutated_dicts = sorted(k for k in dicts_before if k in dicts_after and dicts_before[k] != dicts_after[k])
growth = {k: after.get(k, 0) - before.get(k, 0) for k in set(before) | set(after)}
log_like = {k: g for k, g in growth.items() if g >= ops}   # grew at least one entry per op
total_growth = sum(g for g in growth.values() if g > 0)
if not log_like and total_growth >= ops:                     # e.g. per-account event streams
    log_like = {"<sum of all containers>": total_growth}
out = {"ops": ops, "before": before, "after": after, "growth": growth, "log_like": log_like,
       "total_growth": total_growth, "mutated_dicts": mutated_dicts,
       "state_attrs": sorted(vars(l).keys()) if hasattr(l, "__dict__") else []}
print("PROBE_RESULT " + json.dumps(out))
''')


def _direct_mutations_in_ops(trees) -> int:
    """Count subscript (aug)assignments on self.<attr>[...] lexically inside deposit/withdraw/
    transfer. Event sourcing (even with a cache) mutates state inside a fold/apply step, not in
    the public operations themselves."""
    import ast
    n = 0
    for tree in trees.values():
        for fn in ast.walk(tree):
            if isinstance(fn, ast.FunctionDef) and fn.name in {"deposit", "withdraw", "transfer"}:
                for node in ast.walk(fn):
                    targets = [node.target] if isinstance(node, ast.AugAssign) else (node.targets if isinstance(node, ast.Assign) else [])
                    for t in targets:
                        if (isinstance(t, ast.Subscript) and isinstance(t.value, ast.Attribute)
                                and isinstance(t.value.value, ast.Name) and t.value.value.id == "self"):
                            n += 1
    return n


def detect(workdir: str, python: str = sys.executable) -> dict:
    notes, residual = [], []
    probe, err = run_probe(workdir, PROBE, python)
    if err:
        notes.append(err)
    src = sources(workdir)
    joined = "\n".join(src.values())
    static = {
        "event_words": len(re.findall(r"\b(event|events|replay|fold|project|apply_event|_log|journal)\b", joined, re.I)),
        "class_names": re.findall(r"^class\s+(\w+)", joined, re.M),
        "augassign_on_balance": len(re.findall(r"balances?\[[^\]]+\]\s*[+-]=", joined)),
        "direct_mutations_in_ops": _direct_mutations_in_ops(parse_all(src)),
        "files": sorted(src),
    }
    choice = "none"
    if probe is not None:
        if probe["log_like"]:
            choice = "A"
        else:
            choice = "B"
    # residual / mixed signals
    if choice == "B" and static["event_words"] >= 6:
        residual.append("event-sourcing vocabulary present but no growing operation log")
    if choice == "A" and static["augassign_on_balance"] >= 2:
        # balances mutated in place alongside a log is allowed (cache) but flag it
        notes.append("in-place balance mutation alongside a log (cache or dual state)")
    if (choice == "A" and probe is not None and probe.get("mutated_dicts")
            and static["direct_mutations_in_ops"] >= 2):
        # a growing log AND an instance-level dict that the public operations themselves mutate
        # in place: both approaches live for the same responsibility (dual state), not a cache
        choice = "mixed"
        notes.append("operation log grows per op while deposit/withdraw/transfer mutate instance dict(s) %s directly" % probe["mutated_dicts"])
    return {"choice": choice, "probe": probe, "static": static, "residual": residual, "notes": notes}


if __name__ == "__main__":
    print(json.dumps(detect(sys.argv[1] if len(sys.argv) > 1 else "."), indent=2))
