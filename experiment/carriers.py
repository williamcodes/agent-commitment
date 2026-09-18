#!/usr/bin/env python3
"""Where is the commitment carried? Mechanical indicators per run, from the processed traces and the
final repository. Written before the runs finished; numbers are reported as counts.

Indicators:
  code_mentions_approach   final .py/.md files (excluding tests/SPEC.md) contain "Approach A/B" or the
                           approach's keywords in comments/docstrings (an externalised record of the choice)
  decision_note_files      non-package files the agent created (e.g. NOTES.md, DECISIONS.md)
  fresh_reads_before_write in fresh-session turns 2-4: number of Read/Grep/Bash-cat tool calls on the
                           implementation before the first Write/Edit (did the agent consult the files?)
  cites_existing_code      T3/T4 final messages refer to the existing implementation as a reason
  cites_own_earlier_reason ctx-arm T3/T4 final messages refer back to the T1 decision ("I chose ... at the start")
  plan_events              TodoWrite plan events (explicit harness-managed plans)
  agent_commits            git commits the agent made in the working tree
"""
from __future__ import annotations
import json, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tasks_lib import ROOT, load_task

PROC = os.environ.get("ACX_PROC_BASE", os.path.join(ROOT, "runs", "processed"))
RAW = os.path.join(ROOT, "runs", "raw")
OUT = os.path.join(ROOT, "analysis", "carriers.json")


def run_indicators(r):
    task = load_task(r["task"])
    pkg = task["package"]
    rid = r["run_id"]
    final = os.path.join(RAW, rid, "repo_final")
    mentions, note_files = [], []
    for root, dirs, files in os.walk(final):
        dirs[:] = [d for d in dirs if d not in ("__pycache__", ".git", ".pytest_cache", "tests")]
        for f in files:
            p = os.path.join(root, f); rel = os.path.relpath(p, final)
            if rel == "SPEC.md":
                continue
            if not rel.startswith(pkg + "/") and f.endswith((".md", ".txt", ".rst")):
                note_files.append(rel)
            if f.endswith((".py", ".md", ".txt")):
                try:
                    txt = open(p, encoding="utf-8", errors="replace").read()
                except OSError:
                    continue
                for m in re.finditer(r"[^\n]*\bapproach\s*\(?[ab]\)?\b[^\n]*", txt, re.I):
                    mentions.append({"file": rel, "line": m.group(0).strip()[:160]})
    ev = r["events"]
    fresh = r["arm"].startswith("fresh")
    reads_before_write = {}
    for turn in (2, 3, 4):
        tev = [e for e in ev if e.get("turn") == turn and e["type"] in ("tool_call", "plan")]
        n = 0
        for e in tev:
            if e["tool"] in ("Write", "Edit", "MultiEdit"):
                break
            if e["tool"] in ("Read", "Grep", "Glob") or (e["tool"] == "Bash" and re.search(r"\b(cat|sed|head|tail|grep|ls|find|git (log|show|diff|status))\b", (e.get("input") or {}).get("command", ""))):
                n += 1
        reads_before_write[turn] = n
    msgs34 = " ".join((t.get("final_message") or "") for t in r["turns"] if t["turn"] in (3, 4)).lower()
    cites_existing = bool(re.search(r"\b(existing|current|already)\b[^.\n]{0,60}\b(implementation|code|design|backend|store|structure|module|approach)\b", msgs34))
    cites_own = bool(re.search(r"\b(i|we) (chose|picked|selected|went with|decided|originally|initially)\b|\bat the (start|outset|beginning)\b|\bin (turn|round|step) (1|one)\b|\bearlier (choice|decision|rationale|reasoning)\b|\bmy (original|earlier|initial) (choice|decision|rationale|reasoning)\b", msgs34))
    no_memory = bool(re.search(r"\bno memory\b|\bprevious sessions?\b|\bearlier sessions?\b|\bwithout (a )?(record|history)\b|\bcan't rule out\b|\bcannot rule out\b|\bno evidence (it|that)\b", msgs34))
    agent_commits = 0
    p = os.path.join(RAW, rid, "agent_git_log.txt")
    if os.path.exists(p):
        agent_commits = max(0, sum(1 for l in open(p) if re.match(r"^[0-9a-f]{40} ", l)) - 1)
    return {"run_id": rid, "task": r["task"], "arm": r["arm"], "profile": r["scores"].get("profile"),
            "code_mentions_approach": mentions, "decision_note_files": note_files,
            "reads_before_first_write_by_turn": reads_before_write, "fresh": fresh,
            "cites_existing_code_t3t4": cites_existing, "cites_own_earlier_reason_t3t4": cites_own,
            "acknowledges_no_memory": no_memory, "plan_events": r["counts"]["plans"], "agent_commits": agent_commits,
            "thinking_blocks": r["counts"]["thinking_blocks"]}


def main():
    rows = []
    for f in sorted(os.listdir(PROC)):
        if f.endswith(".json"):
            r = json.load(open(os.path.join(PROC, f)))
            if r["status"] == "complete":
                rows.append(run_indicators(r))
    def cnt(rs, pred): return {"k": sum(1 for r in rs if pred(r)), "n": len(rs)}
    ctx = [r for r in rows if not r["fresh"]]; fresh = [r for r in rows if r["fresh"]]
    agg = {
        "n": len(rows),
        "code_mentions_approach": cnt(rows, lambda r: bool(r["code_mentions_approach"])),
        "code_mentions_approach_ctx": cnt(ctx, lambda r: bool(r["code_mentions_approach"])),
        "code_mentions_approach_fresh": cnt(fresh, lambda r: bool(r["code_mentions_approach"])),
        "decision_note_files": cnt(rows, lambda r: bool(r["decision_note_files"])),
        "plan_events_any": cnt(rows, lambda r: r["plan_events"] > 0),
        "agent_commits_any": cnt(rows, lambda r: r["agent_commits"] > 0),
        "cites_existing_code_ctx": cnt(ctx, lambda r: r["cites_existing_code_t3t4"]),
        "cites_existing_code_fresh": cnt(fresh, lambda r: r["cites_existing_code_t3t4"]),
        "cites_own_earlier_reason_ctx": cnt(ctx, lambda r: r["cites_own_earlier_reason_t3t4"]),
        "cites_own_earlier_reason_fresh": cnt(fresh, lambda r: r["cites_own_earlier_reason_t3t4"]),
        "acknowledges_no_memory_fresh": cnt(fresh, lambda r: r["acknowledges_no_memory"]),
        "fresh_reads_before_write_t3_mean": (sum(r["reads_before_first_write_by_turn"]["3"] if "3" in r["reads_before_first_write_by_turn"] else r["reads_before_first_write_by_turn"][3] for r in fresh) / len(fresh)) if fresh else None,
        "ctx_reads_before_write_t3_mean": (sum(r["reads_before_first_write_by_turn"][3] for r in ctx) / len(ctx)) if ctx else None,
        "fresh_reads_before_write_t3_zero": cnt(fresh, lambda r: r["reads_before_first_write_by_turn"][3] == 0),
        "thinking_blocks_total": sum(r["thinking_blocks"] for r in rows),
        "runs": rows,
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(agg, open(OUT, "w"), indent=1)
    print(json.dumps({k: v for k, v in agg.items() if k != "runs"}, indent=1))


if __name__ == "__main__":
    main()
