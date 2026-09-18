#!/usr/bin/env python3
"""Re-run the CURRENT detectors over every turn-end state of archived runs, reconstructing each state from the
run's snapshots.bundle (harness commits labelled end_tN). Writes detect_final/tN.json next to the original
detect/tN.json and a comparison. process.py prefers detect_final when present and records both.
Usage: ACX_RAW_BASE=runs/v1/raw python experiment/redetect.py"""
from __future__ import annotations
import json, os, re, shutil, subprocess, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tasks_lib import ROOT, load_detector

RAW = os.environ.get("ACX_RAW_BASE", os.path.join(ROOT, "runs", "raw"))
PY = os.path.join(os.environ.get("ACX_VENV_BIN", "/private/tmp/acx-venv/bin"), "python")


def sh(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def main():
    changes = []
    for rid in sorted(os.listdir(RAW)):
        d = os.path.join(RAW, rid)
        mp = os.path.join(d, "meta.json")
        if not os.path.exists(mp) or not os.path.exists(os.path.join(d, "snapshots.bundle")):
            continue
        meta = json.load(open(mp))
        detect = load_detector(meta["task"])
        tmp = tempfile.mkdtemp(prefix="acx-redetect-")
        repo = os.path.join(tmp, "repo.git")
        sh(["git", "clone", "-q", "--bare", os.path.join(d, "snapshots.bundle"), repo])
        # Turn-end states: the snapshot immediately before the next harness "tests_added_t{N+1}" marker (the
        # harness's own end_tN commit is usually a no-op because the last tool-call snapshot already holds the state);
        # T4 = the last snapshot.
        snaps = [json.loads(l) for l in open(os.path.join(d, "snapshots.jsonl")) if l.strip()]
        ends = {}
        for i, sn in enumerate(snaps):
            m = re.match(r"harness:tests_added_t(\d)", sn["label"])
            if m and i > 0:
                ends[int(m.group(1)) - 1] = snaps[i - 1]["commit"]
        if snaps:
            ends[4] = snaps[-1]["commit"]
        os.makedirs(os.path.join(d, "detect_final"), exist_ok=True)
        for t in (1, 2, 3, 4):
            commit = ends.get(t)
            if not commit:
                continue
            wt = os.path.join(tmp, f"t{t}"); os.makedirs(wt)
            p = subprocess.run(["git", "--git-dir", repo, "archive", commit], capture_output=True)
            subprocess.run(["tar", "-x", "-C", wt], input=p.stdout)
            res = detect(wt, PY)
            res["reconstructed_from"] = commit
            json.dump(res, open(os.path.join(d, "detect_final", f"t{t}.json"), "w"), indent=2, default=str)
            old = (meta.get("detections", {}).get(str(t)) or {}).get("choice")
            if old != res["choice"]:
                changes.append({"run_id": rid, "turn": t, "original": old, "final": res["choice"], "notes": res.get("notes")})
        shutil.rmtree(tmp, ignore_errors=True)
        print(rid, [json.load(open(os.path.join(d, "detect_final", f"t{t}.json")))["choice"] if os.path.exists(os.path.join(d, "detect_final", f"t{t}.json")) else None for t in (1, 2, 3, 4)])
    out = os.path.join(RAW, "_redetect_changes.json")
    json.dump(changes, open(out, "w"), indent=1)
    print(f"{len(changes)} changed classifications ->", out)


if __name__ == "__main__":
    main()
