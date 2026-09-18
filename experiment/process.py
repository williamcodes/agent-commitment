#!/usr/bin/env python3
"""Convert raw run directories into processed, annotated run JSON (runs/processed/<run_id>.json).

Processing is mechanical: it extracts a chronological event timeline from the raw stream-json
traces, hook log and filesystem snapshots, attaches the harness's per-turn detector and test results,
parses the agent's stated choice from its final messages, and computes the rubric v1 scores
(experiment/score.py). Nothing here reads results before deciding how to score.
"""
from __future__ import annotations
import json, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tasks_lib import ROOT, load_task
from score import score_run, parse_statement

RAW = os.environ.get("ACX_RAW_BASE", os.path.join(ROOT, "runs", "raw"))
PROC = os.environ.get("ACX_PROC_BASE", os.path.join(ROOT, "runs", "processed"))


def read_jsonl(p):
    if not os.path.exists(p):
        return []
    out = []
    for line in open(p, encoding="utf-8", errors="replace"):
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except Exception:
            pass
    return out


def block_text(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(b.get("text", "") if isinstance(b, dict) else str(b) for b in content)
    return str(content)


def keyword_hits(text, task):
    t = text.lower()
    hits = {"A": [k for k in task["keywords_a"] if k.lower() in t], "B": [k for k in task["keywords_b"] if k.lower() in t]}
    hits["approach_A"] = bool(re.search(r"approach\s*\(?a\)?\b", t)); hits["approach_B"] = bool(re.search(r"approach\s*\(?b\)?\b", t))
    return hits


def extract_turn_events(run_dir, turn, task, arm, target):
    events = []
    stream = read_jsonl(os.path.join(run_dir, "turns", f"t{turn}.stream.jsonl"))
    prompt = open(os.path.join(run_dir, "prompts", f"t{turn}.md"), encoding="utf-8").read() if os.path.exists(os.path.join(run_dir, "prompts", f"t{turn}.md")) else ""
    init = next((e for e in stream if e.get("type") == "system" and e.get("subtype") == "init"), None)
    first_ts = next((e.get("timestamp") for e in stream if e.get("timestamp")), None)
    kind = None
    if turn == 3:
        kind = "irrelevant_temptation" if arm.endswith("tempt") else "decisive_evidence"
    events.append({"type": "prompt", "turn": turn, "ts": first_ts, "text": prompt, "challenge": kind, "target": target,
                   "session_id": init.get("session_id") if init else None})
    if init:
        events.append({"type": "harness", "turn": turn, "ts": first_ts, "subtype": "session_init",
                       "model": init.get("model"), "session_id": init.get("session_id"), "tools": init.get("tools"),
                       "permission_mode": init.get("permissionMode"), "cwd": init.get("cwd"), "claude_code_version": init.get("claude_code_version")})
    final_text = None
    for ev in stream:
        t = ev.get("type")
        ts = ev.get("timestamp")
        if t == "assistant":
            for b in ev["message"].get("content", []):
                bt = b.get("type")
                if bt == "text" and b.get("text", "").strip():
                    final_text = b["text"]
                    events.append({"type": "message", "turn": turn, "ts": ts, "text": b["text"], "uuid": ev.get("uuid"), "keywords": keyword_hits(b["text"], task)})
                elif bt == "thinking":
                    events.append({"type": "thinking", "turn": turn, "ts": ts, "uuid": ev.get("uuid"),
                                   "content_exposed": bool(b.get("thinking")), "text": b.get("thinking") or "",
                                   "note": "Claude Code emits thinking blocks with redacted (empty) content; only their occurrence is observable."})
                elif bt == "tool_use":
                    e = {"type": "tool_call", "turn": turn, "ts": ts, "tool": b.get("name"), "tool_use_id": b.get("id"), "input": b.get("input"), "uuid": ev.get("uuid")}
                    if b.get("name") == "TodoWrite":
                        e["type"] = "plan"
                    events.append(e)
        elif t == "user":
            for b in ev["message"].get("content", []) if isinstance(ev["message"].get("content"), list) else []:
                if isinstance(b, dict) and b.get("type") == "tool_result":
                    events.append({"type": "tool_result", "turn": turn, "ts": ts, "tool_use_id": b.get("tool_use_id"),
                                   "is_error": bool(b.get("is_error")), "text": block_text(b.get("content")), "uuid": ev.get("uuid")})
        elif t == "result":
            events.append({"type": "harness", "turn": turn, "ts": ts, "subtype": "turn_result", "num_agent_turns": ev.get("num_turns"),
                           "cost_usd": ev.get("total_cost_usd"), "duration_ms": ev.get("duration_ms"), "is_error": ev.get("is_error"),
                           "stop_reason": ev.get("stop_reason"), "result_subtype": ev.get("subtype")})
            if ev.get("result"):
                final_text = ev["result"]
    return events, final_text, prompt


def strip_noise(diff: str) -> str:
    """Drop diff sections for __pycache__/.pytest_cache/.pyc files (binary noise)."""
    out, keep = [], True
    for line in diff.split("\n"):
        if line.startswith("diff --git"):
            keep = not any(x in line for x in ("__pycache__", ".pytest_cache", ".pyc"))
        if keep:
            out.append(line)
    return "\n".join(out)


def process_run(run_id):
    run_dir = os.path.join(RAW, run_id)
    meta = json.load(open(os.path.join(run_dir, "meta.json")))
    task = load_task(meta["task"])
    events, turns = [], []
    hooks = read_jsonl(os.path.join(run_dir, "hooks.jsonl"))
    snaps = read_jsonl(os.path.join(run_dir, "snapshots.jsonl"))
    for tinfo in meta["turns"]:
        turn = tinfo["turn"]
        target = meta.get("target_for_t3") if turn == 3 else None
        tev, final_text, prompt = extract_turn_events(run_dir, turn, task, meta["arm"], target)
        det = meta["detections"].get(str(turn), {})
        tests = meta["tests"].get(str(turn), {})
        st = parse_statement(final_text or "", task, turn)
        tev.append({"type": "tests", "turn": turn, "ts": tinfo.get("ended"), "passed": tests.get("passed"), "total": tests.get("total"),
                    "failed": tests.get("failed"), "errors": tests.get("errors"), "per_file": tests.get("per_file"), "tests_modified": tests.get("tests_modified")})
        tev.append({"type": "detection", "turn": turn, "ts": tinfo.get("ended"), "choice": det.get("choice"), "residual": det.get("residual"),
                    "notes": det.get("notes"), "probe": det.get("probe"), "static": det.get("static")})
        mem = meta.get("memory", {}).get(str(turn), {})
        if mem.get("files"):
            tev.append({"type": "harness", "turn": turn, "ts": tinfo.get("ended"), "subtype": "auto_memory_files", "files": mem["files"], "wiped": mem.get("wiped", False)})
        turns.append({"turn": turn, "prompt": prompt, "started": tinfo.get("started"), "ended": tinfo.get("ended"), "seconds": tinfo.get("seconds"),
                      "session_id": tinfo.get("session_id"), "resumed_session": tinfo.get("resume_session"), "cost_usd": tinfo.get("cost_usd"),
                      "num_agent_turns": tinfo.get("num_agent_turns"), "timed_out": tinfo.get("timed_out"), "returncode": tinfo.get("returncode"),
                      "final_message": final_text, "detection": det.get("choice"), "detection_residual": det.get("residual"), "detection_notes": det.get("notes"),
                      "tests": {k: tests.get(k) for k in ("passed", "total", "failed", "errors", "per_file", "tests_modified")},
                      "statement": st, "challenge": ("irrelevant_temptation" if meta["arm"].endswith("tempt") else "decisive_evidence") if turn == 3 else None,
                      "target": target})
        events.extend(tev)
    # filesystem snapshots (from the PostToolUse hook + harness boundaries)
    by_tool_id = {}
    for s in snaps:
        files = [f for f in s["files"] if not any(x in (f[-1] if f else "") for x in ("__pycache__", ".pytest_cache", ".pyc"))]
        if not files:
            continue  # only bytecode/cache noise changed
        e = {"type": "fs_change", "ts": s["ts"], "label": s["label"], "tool_use_id": s.get("tool_use_id") or None,
             "files": files, "diff": strip_noise(s["diff"]), "seq_snapshot": s["seq"]}
        events.append(e)
    # assign turn to fs events by timestamp windows
    windows = [(t["started"], t["ended"], t["turn"]) for t in meta["turns"]]
    for e in events:
        if e["type"] == "fs_change":
            e["turn"] = next((tn for (a, b, tn) in windows if a and b and a <= e["ts"] <= b), None)
            if e["turn"] is None:
                # harness snapshots at boundaries: attribute to the following turn (tests added) or previous (end)
                lab = e["label"]
                m = re.search(r"t(\d)", lab)
                e["turn"] = int(m.group(1)) if m else 0
    # chronological order: by turn, then ts; prompts first within a turn
    order = {"prompt": 0, "harness": 1, "thinking": 2, "message": 3, "plan": 4, "tool_call": 4, "tool_result": 5, "fs_change": 6, "tests": 8, "detection": 9}
    events.sort(key=lambda e: (e.get("turn") or 0, e.get("ts") or "", order.get(e["type"], 5)))
    for i, e in enumerate(events):
        e["seq"] = i
    # link tool results to calls, and fs changes to tool calls
    calls = {e["tool_use_id"]: e for e in events if e["type"] in ("tool_call", "plan")}
    for e in events:
        if e["type"] == "tool_result" and e.get("tool_use_id") in calls:
            e["tool"] = calls[e["tool_use_id"]]["tool"]
        if e["type"] == "fs_change" and e.get("tool_use_id") in calls:
            e["tool"] = calls[e["tool_use_id"]]["tool"]
    scores = score_run(meta, turns, task)
    out = {"run_id": run_id, "task": meta["task"], "task_name": task["name"], "domain": task["domain"], "arm": meta["arm"], "rep": meta["rep"],
           "model": meta["model"], "claude_version": meta.get("claude_version"), "status": meta["status"], "started": meta["started"], "ended": meta.get("ended"),
           "total_cost_usd": meta.get("total_cost_usd"), "experiment_commit": meta.get("experiment_commit"), "context_mode": meta.get("context_mode"),
           "challenge": meta.get("challenge"), "target_for_t3": meta.get("target_for_t3"), "target_fallback_used": meta.get("target_fallback_used"),
           "approach_a": task["approach_a"], "approach_b": task["approach_b"], "turns": turns, "scores": scores,
           "counts": {"tool_calls": sum(e["type"] in ("tool_call", "plan") for e in events), "messages": sum(e["type"] == "message" for e in events),
                      "fs_changes": sum(e["type"] == "fs_change" for e in events), "thinking_blocks": sum(e["type"] == "thinking" for e in events),
                      "plans": sum(e["type"] == "plan" for e in events)},
           "events": events, "raw_dir": f"runs/raw/{run_id}"}
    return out


def main():
    os.makedirs(PROC, exist_ok=True)
    ids = [d for d in sorted(os.listdir(RAW)) if os.path.exists(os.path.join(RAW, d, "meta.json"))]
    if len(sys.argv) > 1:
        ids = [i for i in ids if i in sys.argv[1:]]
    for rid in ids:
        out = process_run(rid)
        with open(os.path.join(PROC, rid + ".json"), "w") as f:
            json.dump(out, f, indent=1, default=str)
        print(rid, out["status"], out["scores"].get("profile"), [t["detection"] for t in out["turns"]])


if __name__ == "__main__":
    main()
