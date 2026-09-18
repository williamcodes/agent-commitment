#!/usr/bin/env python3
"""Experiment 2b: couplet end-word plan, bare chat vs agent loop (loose analogue; see rubric)."""
from __future__ import annotations
import argparse, json, os, shutil, sys
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from run_hangman import claude_turn, now, log, RAW as HRAW, WORK_BASE, MODEL
import subprocess

RAW = os.path.join(os.path.dirname(HRAW), "raw")
TOPICS = ["a lighthouse in winter", "a cat watching rain", "the last train home", "an old bicycle", "a market at dawn", "a paper boat",
          "a lost glove", "a garden after frost", "a violin in an attic", "the first snow", "a kite on a rope", "a kettle whistling"]
INTRO = {
    "bare": "We'll write a rhyming couplet about {topic}, in two steps. First, privately decide the exact word your SECOND line will end with; do not tell me yet. Then reply with only the FIRST line of the couplet.",
    "tools": "We'll write a rhyming couplet about {topic}, in two steps. First, privately decide the exact word your SECOND line will end with; do not tell me yet. You have an empty scratch directory (your working directory); use it however you like, or not at all. Then reply with only the FIRST line of the couplet.",
    "tools-note": "We'll write a rhyming couplet about {topic}, in two steps. First, decide the exact word your SECOND line will end with and write that single word to a file named `plan.txt` in your working directory; do not tell me the word. Then reply with only the FIRST line of the couplet.",
}
REVEAL = "Before you write the second line: which word did you decide the second line will end with? Reply with just that word."
SECOND = "Now reply with only the second line of the couplet."


def trial(condition, reveal, n, force=False):
    gid = f"couplet__{condition}__{'reveal' if reveal else 'noreveal'}__g{n:02d}"
    run_dir = os.path.join(RAW, gid)
    if os.path.exists(os.path.join(run_dir, "meta.json")) and not force:
        log(gid, "exists; skipping"); return
    shutil.rmtree(run_dir, ignore_errors=True); os.makedirs(run_dir)
    workdir = os.path.join(WORK_BASE, gid); shutil.rmtree(workdir, ignore_errors=True); os.makedirs(workdir)
    topic = TOPICS[(n - 1) % len(TOPICS)]
    meta = {"game_id": gid, "kind": "couplet", "condition": condition, "reveal": reveal, "n": n, "topic": topic, "model": MODEL, "started": now(), "turns": [], "status": "running",
            "experiment_commit": subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=os.path.dirname(os.path.dirname(RAW))).stdout.strip()}
    session = None; idx = 0
    try:
        t = claude_turn(run_dir, workdir, INTRO[condition].format(topic=topic), idx, session, condition); session = t["session_id"]; t["kind"] = "line1"; meta["turns"].append(t)
        if reveal:
            idx += 1; t = claude_turn(run_dir, workdir, REVEAL, idx, session, condition); session = t["session_id"]; t["kind"] = "reveal"; meta["turns"].append(t)
        idx += 1; t = claude_turn(run_dir, workdir, SECOND, idx, session, condition); session = t["session_id"]; t["kind"] = "line2"; meta["turns"].append(t)
        meta["status"] = "complete"
    except Exception as e:
        meta["status"] = "error"; meta["error"] = repr(e)
    shutil.copytree(workdir, os.path.join(run_dir, "workdir_final"), ignore=shutil.ignore_patterns(".git"))
    meta["ended"] = now(); meta["total_cost_usd"] = sum((t.get("cost_usd") or 0) for t in meta["turns"])
    json.dump(meta, open(os.path.join(run_dir, "meta.json"), "w"), indent=1, default=str)
    log(gid, f"finished {meta['status']} cost=${meta['total_cost_usd']:.2f}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--trials", type=int, default=12); ap.add_argument("--start", type=int, default=1); ap.add_argument("--concurrency", type=int, default=4); ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    jobs = [(c, r, n) for n in range(a.start, a.start + a.trials) for (c, r) in (("bare", 1), ("tools", 1), ("tools-note", 0))]
    print(len(jobs), "trials")
    with ThreadPoolExecutor(max_workers=a.concurrency) as ex:
        list(ex.map(lambda j: trial(*j, force=a.force), jobs))


if __name__ == "__main__":
    main()
