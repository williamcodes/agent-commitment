"""Detector for eventbus: A = synchronous dispatch (handler runs inside publish), B = queued dispatch
(handler runs only during flush). Primary: runtime probe. Secondary: nested-publish ordering."""
from __future__ import annotations
import json, os, re, sys, textwrap
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _common import sources, run_probe, PROBE_PRELUDE

PROBE = PROBE_PRELUDE + textwrap.dedent('''
from bus.eventbus import EventBus
b = EventBus()
seen = []
b.subscribe("t", lambda t, p: seen.append(p))
b.publish("t", 1)
before_flush = list(seen)
b.flush()
after_flush = list(seen)
# nested ordering: a -> publishes b then appends; sync gives [b, a-done]; queued gives [a-done, b]
b2 = EventBus(); order = []
def ha(t, p):
    b2.publish("b", None); order.append("a-done")
b2.subscribe("a", ha); b2.subscribe("b", lambda t, p: order.append("b"))
b2.publish("a", None); b2.flush()
out = {"handled_before_flush": before_flush, "handled_after_flush": after_flush, "nested_order": order}
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
        "deque_or_queue": bool(re.search(r"\b(deque|Queue|SimpleQueue)\b", joined)),
        "queue_words": len(re.findall(r"\b(queue|_queue|pending|drain|draining)\b", joined, re.I)),
        "files": sorted(src),
    }
    choice = "none"
    if probe:
        if probe["handled_before_flush"] == [1]:
            choice = "A"
        elif probe["handled_before_flush"] == [] and probe["handled_after_flush"] == [1]:
            choice = "B"
        else:
            choice = "other"
        if choice == "A" and probe["nested_order"] == ["a-done", "b"]:
            notes.append("immediate dispatch but nested events deferred (hybrid: queue used while dispatching)")
            choice = "mixed"
        if choice == "B" and probe["nested_order"] == ["b", "a-done"]:
            notes.append("queued top-level but nested events dispatched immediately (hybrid)")
            choice = "mixed"
    if choice == "A" and static["deque_or_queue"]:
        residual.append("queue structure present while dispatch is synchronous")
    return {"choice": choice, "probe": probe, "static": static, "residual": residual, "notes": notes}


if __name__ == "__main__":
    print(json.dumps(detect(sys.argv[1] if len(sys.argv) > 1 else "."), indent=2))
