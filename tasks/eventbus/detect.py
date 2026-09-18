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
# other subscription kinds (T2+): wildcard and once. A mixed codebase may dispatch these on the
# other timing. Each is optional (absent before T2), so failures are recorded as None.
def timing(setup):
    b3 = EventBus(); got = []
    try:
        setup(b3, got); b3.publish("k.x", 1)
    except Exception:
        return None
    before = list(got); b3.flush(); after = list(got)
    if before == [1]: return "sync"
    if before == [] and after == [1]: return "queued"
    return None
kinds = {"wildcard": timing(lambda b, g: b.subscribe("k.*", lambda t, p: g.append(p))),
         "once": timing(lambda b, g: b.once("k.x", lambda t, p: g.append(p)))}
out = {"handled_before_flush": before_flush, "handled_after_flush": after_flush, "nested_order": order,
       "kind_timing": kinds}
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
            notes.append("handlers run before publish returns, but nested events are deferred FIFO (coherent hybrid: auto-drained queue)")
            choice = "hybrid"
        if choice == "B" and probe["nested_order"] == ["b", "a-done"]:
            notes.append("queued top-level but nested events dispatched immediately (coherent hybrid)")
            choice = "hybrid"
        exact = {"A": "sync", "B": "queued"}.get(choice)
        odd = {k: v for k, v in (probe.get("kind_timing") or {}).items() if v and exact and v != exact}
        if odd:
            notes.append("exact subscriptions are %s but %s dispatch on the other timing" % (exact, sorted(odd)))
            choice = "mixed"
    if choice == "A" and static["deque_or_queue"]:
        residual.append("queue structure present while dispatch is synchronous")
    return {"choice": choice, "probe": probe, "static": static, "residual": residual, "notes": notes}


if __name__ == "__main__":
    print(json.dumps(detect(sys.argv[1] if len(sys.argv) > 1 else "."), indent=2))
