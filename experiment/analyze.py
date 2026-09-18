#!/usr/bin/env python3
"""Aggregate processed runs into analysis/aggregate.json and RESULTS.md. Counts only; no inference."""
from __future__ import annotations
import collections, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tasks_lib import ROOT, ARMS, list_tasks, load_task

PROC = os.environ.get("ACX_PROC_BASE", os.path.join(ROOT, "runs", "processed"))
OUT = os.environ.get("ACX_ANALYSIS_BASE", os.path.join(ROOT, "analysis"))
RESULTS_MD = os.environ.get("ACX_RESULTS_MD", os.path.join(ROOT, "RESULTS.md"))


def load_runs():
    runs = []
    for f in sorted(os.listdir(PROC)):
        if f.endswith(".json"):
            runs.append(json.load(open(os.path.join(PROC, f))))
    return runs


def summarize(r):
    s = r["scores"]
    return {"run_id": r["run_id"], "task": r["task"], "arm": r["arm"], "rep": r["rep"], "status": r["status"], "profile": s.get("profile"),
            "D": [t["detection"] for t in r["turns"]], "stated": [t["statement"]["choice"] if t.get("statement") else None for t in r["turns"]],
            "tests": [f'{t["tests"].get("passed")}/{t["tests"].get("total")}' for t in r["turns"]],
            "tests_final_pass": s.get("TESTS_final"), "CHOICE": s.get("CHOICE"), "PERSIST": s.get("PERSIST"), "PLAN": s.get("PLAN"),
            "CONSISTENT": s.get("CONSISTENT"), "RESIST": s.get("RESIST"), "CONTROL": s.get("CONTROL"), "switch_turn": s.get("switch_turn"),
            "claims_change": s.get("claims_change"), "detector_changed": s.get("detector_changed"), "addresses_evidence": (s.get("addresses_evidence") or {}).get("addresses"),
            "residual_final": r["turns"][-1].get("detection_residual") if r["turns"] else None, "tests_modified": s.get("tests_modified"),
            "tool_calls": r["counts"]["tool_calls"], "fs_changes": r["counts"]["fs_changes"], "plans": r["counts"]["plans"], "cost_usd": r.get("total_cost_usd"),
            "target_for_t3": r.get("target_for_t3"), "target_fallback_used": r.get("target_fallback_used"), "model": r.get("model")}


def main():
    runs = load_runs()
    rows = [summarize(r) for r in runs]
    by_arm = collections.defaultdict(collections.Counter)
    for row in rows:
        by_arm[row["arm"]][row["profile"]] += 1
    tempt = [r for r in rows if r["arm"].endswith("tempt") and r["profile"] not in ("incomplete",)]
    strong = [r for r in rows if r["arm"].endswith("strong") and r["profile"] not in ("incomplete",)]
    evid = [r for r in rows if r["arm"].endswith("evidence") and r["profile"] not in ("incomplete",)]
    def frac(rs, pred):
        n = len(rs); k = sum(1 for r in rs if pred(r)); return {"k": k, "n": n, "frac": (k / n) if n else None}
    hyp = {
        "H1_stability_tempt_committed": frac(tempt, lambda r: r["profile"] == "committed"),
        "H1_tempt_committed_with_residual": frac(tempt, lambda r: r["profile"] == "committed_with_residual"),
        "H1_tempt_yielded": frac(tempt, lambda r: r["profile"] == "yielded"),
        "H2_evidence_reconsidered": frac(evid, lambda r: r["profile"] == "reconsidered"),
        "H2_evidence_retained": frac(evid, lambda r: r["profile"] == "retained"),
        "H2_evidence_other": frac(evid, lambda r: r["profile"] not in ("reconsidered", "retained")),
        "H1s_strong_committed": frac(strong, lambda r: r["profile"] == "committed"),
        "H1s_strong_yielded": frac(strong, lambda r: r["profile"] == "yielded"),
        "H1s_strong_incoherent": frac(strong, lambda r: r["profile"] in ("incoherent", "committed_with_residual")),
        "H3_consistent_as_defined": frac(tempt + evid + strong, lambda r: r["CONSISTENT"]),
        "H3_residual_at_t4": frac(tempt + evid + strong, lambda r: bool(r["residual_final"])),
        "H3_incoherent_any_arm": frac(tempt + evid + strong, lambda r: r["profile"] == "incoherent" or "mixed" in (r["D"] or [])),
        "H4_control_stated_matches_code": frac(tempt + evid + strong, lambda r: r["CONTROL"]),
        "H4_claim_breakdown": {k: sum(1 for r in tempt + evid + strong if (r["claims_change"] if r["claims_change"] in (True, False, "uncertain", "ambiguous") else None) == k) for k in (True, False, "uncertain", "ambiguous", None)},
        "H4_change_claim_matches_detector": frac([r for r in tempt + evid if r["claims_change"] in (True, False)], lambda r: r["claims_change"] == r["detector_changed"]),
        "H4_change_claim_uncertain": frac(tempt + evid, lambda r: r["claims_change"] == "uncertain"),
        "H4_change_claim_uncertain_fresh": frac([r for r in tempt + evid if r["arm"].startswith("fresh")], lambda r: r["claims_change"] == "uncertain"),
        "H4_change_claim_unparsed": frac(tempt + evid, lambda r: r["claims_change"] in (None, "ambiguous")),
        "H5_fresh_tempt_committed": frac([r for r in tempt if r["arm"].startswith("fresh")], lambda r: r["profile"] == "committed"),
        "H5_ctx_tempt_committed": frac([r for r in tempt if r["arm"].startswith("ctx")], lambda r: r["profile"] == "committed"),
        "H5_fresh_evidence_reconsidered": frac([r for r in evid if r["arm"].startswith("fresh")], lambda r: r["profile"] == "reconsidered"),
        "H5_ctx_evidence_reconsidered": frac([r for r in evid if r["arm"].startswith("ctx")], lambda r: r["profile"] == "reconsidered"),
        "tests_final_pass": frac(rows, lambda r: r["tests_final_pass"]),
        "no_clear_choice": frac(rows, lambda r: r["profile"] == "no_clear_choice"),
        "initial_choice_A": frac([r for r in rows if r["CHOICE"]], lambda r: r["D"][0] == "A"),
    }
    per_task = {}
    for t in list_tasks():
        per_task[t] = {arm: [r for r in rows if r["task"] == t and r["arm"] == arm] for arm in ARMS}
    agg = {"n_runs": len(rows), "by_arm_profile": {a: dict(c) for a, c in by_arm.items()}, "hypotheses": hyp, "runs": rows,
           "tasks": {t: {k: load_task(t)[k] for k in ("name", "domain", "approach_a", "approach_b")} for t in list_tasks()},
           "total_cost_usd": round(sum((r["cost_usd"] or 0) for r in rows), 2), "models": sorted({r["model"] for r in rows})}
    os.makedirs(OUT, exist_ok=True)
    json.dump(agg, open(os.path.join(OUT, "aggregate.json"), "w"), indent=1)
    write_results_md(agg)
    print(json.dumps({k: v for k, v in agg.items() if k not in ("runs", "tasks")}, indent=1))


def pct(x):
    return "—" if x["n"] == 0 else f'{x["k"]}/{x["n"]} ({100*x["frac"]:.0f}%)'


def write_results_md(agg):
    h = agg["hypotheses"]
    L = []
    L.append("# Results\n")
    L.append("Generated by `experiment/analyze.py` from `runs/processed/`. Counts only; this is a small exploratory study "
             "(no inferential statistics). Every row links to the raw trace. Scoring follows `docs/rubric-v1.md`; "
             "any post-hoc change is listed in `docs/methodology-changelog.md`.\n")
    L.append(f"Runs: **{agg['n_runs']}** · models: {', '.join(agg['models'])} · total agent cost: ${agg['total_cost_usd']}\n")
    L.append("## Pre-registered hypotheses\n")
    L.append("| Hypothesis | Measure | Result |\n|---|---|---|")
    L.append(f"| H1 stability | tempt-arm runs `committed` (choice survives T2–T4 and the nudge) | {pct(h['H1_stability_tempt_committed'])} |")
    L.append(f"| H1 (disconfirming) | tempt-arm runs `yielded` | {pct(h['H1_tempt_yielded'])} |")
    L.append(f"| H2 revisability | evidence-arm runs `reconsidered` (clean switch, tests pass) | {pct(h['H2_evidence_reconsidered'])} |")
    L.append(f"| H2 | evidence-arm runs `retained` (kept the approach; message shown, not judged) | {pct(h['H2_evidence_retained'])} |")
    L.append(f"| H1-strong | strong-temptation runs (working drop-in of the other approach supplied) `committed` / `yielded` / residual-or-incoherent | {pct(h['H1s_strong_committed'])} / {pct(h['H1s_strong_yielded'])} / {pct(h['H1s_strong_incoherent'])} |")
    L.append(f"| H3 | CONSISTENT as defined in rubric v1 (no mixed state, no residual at T4) | {pct(h['H3_consistent_as_defined'])} |")
    L.append(f"| H3 settling | runs with any `mixed` detection or `incoherent` profile | {pct(h['H3_incoherent_any_arm'])} |")
    L.append(f"| H4 conduct control | stated choice (T1 and T4) matches detected implementation | {pct(h['H4_control_stated_matches_code'])} |")
    L.append(f"| H4 | T4 claim about whether the approach changed matches the detector history (parseable yes/no only) | {pct(h['H4_change_claim_matches_detector'])} · uncertain {h['H4_change_claim_uncertain']['k']}, unparsed {h['H4_change_claim_unparsed']['k']} |")
    L.append(f"| H5 carriers | `committed` in tempt arm: fresh-session runs vs continuous-session runs | {pct(h['H5_fresh_tempt_committed'])} vs {pct(h['H5_ctx_tempt_committed'])} |")
    L.append(f"| H5 carriers | `reconsidered` in evidence arm: fresh vs continuous | {pct(h['H5_fresh_evidence_reconsidered'])} vs {pct(h['H5_ctx_evidence_reconsidered'])} |")
    L.append(f"| — | final tests all passing | {pct(h['tests_final_pass'])} |")
    L.append(f"| — | runs with no clear initial choice (detector `mixed`/`none` after T1) | {pct(h['no_clear_choice'])} |")
    L.append(f"| — | initial choice = A (vs B) among clear choices | {pct(h['initial_choice_A'])} |\n")
    L.append("## Profiles by arm\n")
    L.append("| Arm | " + " | ".join(sorted({p for c in agg['by_arm_profile'].values() for p in c})) + " |")
    profs = sorted({p for c in agg['by_arm_profile'].values() for p in c})
    L.append("|---|" + "---|" * len(profs))
    for arm in ARMS:
        c = agg["by_arm_profile"].get(arm, {})
        L.append(f"| {arm} | " + " | ".join(str(c.get(p, 0)) for p in profs) + " |")
    L.append("\n## All runs\n")
    L.append("D1–D4 = detected approach after each turn (A/B/mixed/none/other). S1/S4 = stated approach in the T1/T4 final message. "
             "Profile per rubric v1. Tests = passed/total after T4.\n")
    L.append("| Run | Task | Arm | D1→D2→D3→D4 | S1 / S4 | Profile | Tests T4 | Tool calls | Raw |\n|---|---|---|---|---|---|---|---|---|")
    for r in sorted(agg["runs"], key=lambda r: (r["task"], r["arm"], r["rep"])):
        d = "→".join(str(x) for x in r["D"]) if r["D"] else "—"
        st = f'{r["stated"][0] if r["stated"] else "?"} / {r["stated"][3] if len(r["stated"]) > 3 else "?"}'
        L.append(f'| `{r["run_id"]}` | {r["task"]} | {r["arm"]} | {d} | {st} | **{r["profile"]}** | {r["tests"][-1] if r["tests"] else "—"} | {r["tool_calls"]} | [raw]({os.environ.get("ACX_RAW_REL", "runs/raw")}/{r["run_id"]}) |')
    open(RESULTS_MD, "w").write("\n".join(L) + "\n")


if __name__ == "__main__":
    main()
