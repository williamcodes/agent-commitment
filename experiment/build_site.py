#!/usr/bin/env python3
"""Generate static JSON for the GitHub Pages site from runs/processed and analysis/aggregate.json.
Large tool results and diffs are truncated for the browser with an explicit flag and a link to the raw
file, so nothing is hidden; the raw trace remains the source of truth."""
from __future__ import annotations
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tasks_lib import ROOT, ARMS, list_tasks, load_task

PROC = os.environ.get("ACX_PROC_BASE", os.path.join(ROOT, "runs", "processed"))
DATASET = os.environ.get("ACX_DATASET", "v2")          # "v2" (headline) or "v1" (superseded)
SITE = os.path.join(ROOT, "site", "data") if DATASET == "v2" else os.path.join(ROOT, "site", "data", DATASET)
RAW = os.environ.get("ACX_RAW_BASE", os.path.join(ROOT, "runs", "raw"))
ANALYSIS = os.environ.get("ACX_ANALYSIS_BASE", os.path.join(ROOT, "analysis"))
RAW_REL = os.environ.get("ACX_RAW_REL", "runs/raw")
MAX_TEXT = 20000
MAX_DIFF = 60000
GITHUB = os.environ.get("ACX_GITHUB_URL", "https://github.com/williamcodes/agent-commitment")


def trunc(s, n):
    if s is None:
        return None, False
    if len(s) <= n:
        return s, False
    return s[:n] + f"\n… [truncated {len(s)-n} characters; see raw trace]", True


def final_files(run_id):
    base = os.path.join(RAW, run_id, "repo_final")
    out = {}
    for root, dirs, files in os.walk(base):
        dirs[:] = [d for d in dirs if d not in ("__pycache__", ".git", ".pytest_cache")]
        for f in files:
            p = os.path.join(root, f)
            rel = os.path.relpath(p, base)
            if os.path.getsize(p) < 80000 and f.endswith((".py", ".md", ".txt", ".toml", ".cfg", ".json", ".yaml", ".yml")):
                out[rel] = open(p, encoding="utf-8", errors="replace").read()
            else:
                out[rel] = None
    return out


def main():
    os.makedirs(os.path.join(SITE, "runs"), exist_ok=True)
    agg = json.load(open(os.path.join(ANALYSIS, "aggregate.json")))
    carriers = json.load(open(os.path.join(ANALYSIS, "carriers.json"))) if os.path.exists(os.path.join(ANALYSIS, "carriers.json")) else {}
    runs_index = []
    for f in sorted(os.listdir(PROC)):
        if not f.endswith(".json"):
            continue
        r = json.load(open(os.path.join(PROC, f)))
        events = []
        for e in r["events"]:
            e = dict(e)
            if e["type"] in ("tool_result", "message", "thinking"):
                e["text"], e["truncated"] = trunc(e.get("text"), MAX_TEXT)
            if e["type"] == "fs_change":
                e["diff"], e["truncated"] = trunc(e.get("diff"), MAX_DIFF)
            if e["type"] in ("tool_call", "plan") and isinstance(e.get("input"), dict):
                inp = {}
                for k, v in e["input"].items():
                    if isinstance(v, str):
                        v, t = trunc(v, MAX_TEXT)
                    inp[k] = v
                e["input"] = inp
            if e["type"] == "detection":
                e.pop("probe", None); e.pop("static", None)
            events.append(e)
        out = dict(r); out["events"] = events
        out["final_files"] = final_files(r["run_id"])
        out["raw_url"] = f"{GITHUB}/tree/main/{RAW_REL}/{r['run_id']}"
        out["detections_full"] = {t["turn"]: {"choice": t["detection"], "residual": t.get("detection_residual"), "notes": t.get("detection_notes")} for t in r["turns"]}
        # full detector output (probe + static) per turn from raw
        det_dir = os.path.join(RAW, r["run_id"], "detect")
        if os.path.isdir(det_dir):
            for df in sorted(os.listdir(det_dir)):
                out["detections_full"][int(df[1])].update(json.load(open(os.path.join(det_dir, df))))
        json.dump(out, open(os.path.join(SITE, "runs", r["run_id"] + ".json"), "w"), default=str)
        s = r["scores"]
        runs_index.append({"run_id": r["run_id"], "task": r["task"], "task_name": r["task_name"], "arm": r["arm"], "rep": r["rep"], "status": r["status"],
                           "profile": s.get("profile"), "D": [t["detection"] for t in r["turns"]], "stated": [(t.get("statement") or {}).get("choice") for t in r["turns"]],
                           "tests": [[t["tests"].get("passed"), t["tests"].get("total")] for t in r["turns"]], "switch_turn": s.get("switch_turn"),
                           "CONTROL": s.get("CONTROL"), "claims_change": s.get("claims_change"), "detector_changed": s.get("detector_changed"),
                           "tool_calls": r["counts"]["tool_calls"], "fs_changes": r["counts"]["fs_changes"], "plans": r["counts"]["plans"],
                           "cost_usd": r.get("total_cost_usd"), "target_for_t3": r.get("target_for_t3"), "model": r.get("model"),
                           "residual_final": r["turns"][-1].get("detection_residual") if r["turns"] else None,
                           "addresses_evidence": (s.get("addresses_evidence") or {}).get("addresses"), "tests_modified": s.get("tests_modified")})
    tasks = {}
    for t in list_tasks():
        tk = load_task(t)
        tasks[t] = {k: tk[k] for k in ("id", "name", "domain", "package", "approach_a", "approach_b")}
        tasks[t]["turns"] = tk["turns"]
        tasks[t]["spec"] = open(os.path.join(tk["starter"], "SPEC.md")).read()
        tasks[t]["detector_source"] = open(os.path.join(tk["dir"], "detect.py")).read()
    index = {"generated": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(), "github": GITHUB, "arms": ARMS, "tasks": tasks, "runs": runs_index,
             "dataset": DATASET, "raw_rel": RAW_REL,
             "aggregate": {k: v for k, v in agg.items() if k not in ("runs", "tasks")}, "carriers": {k: v for k, v in carriers.items() if k != "runs"},
             "rubric_md": open(os.path.join(ROOT, "docs", "rubric-v1.md")).read(),
             "changelog_md": open(os.path.join(ROOT, "docs", "methodology-changelog.md")).read(),
             "williams_md": open(os.path.join(ROOT, "docs", "williams-commitment.md")).read()}
    for extra in ("METHODOLOGY.md", "docs/limitations.md", "RESULTS.md", "RESULTS-v1.md", "docs/analysis.md", "docs/review/skeptical-review.md", "docs/review/pre-run-validation.md", "docs/review/mixed-validation.md", "docs/rubric-v1.1-amendment.md", "docs/rubric-hangman-v1.md", "docs/experiment2-hangman.md"):
        p = os.path.join(ROOT, extra)
        if os.path.exists(p):
            index[extra.replace("/", "_").replace(".md", "_md")] = open(p).read()
    other = os.path.join(ROOT, "analysis", "v1", "aggregate.json") if DATASET == "v2" else os.path.join(ROOT, "analysis", "aggregate.json")
    if os.path.exists(other):
        oa = json.load(open(other)); index["other_dataset"] = {"name": "v1" if DATASET == "v2" else "v2", "aggregate": {k: v for k, v in oa.items() if k not in ("runs", "tasks")}}
    json.dump(index, open(os.path.join(SITE, "index.json"), "w"), default=str)
    print("site data:", len(runs_index), "runs")


if __name__ == "__main__":
    main()
