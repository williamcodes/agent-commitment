#!/usr/bin/env python3
"""Score Experiment 2 games mechanically per docs/rubric-hangman-v1.md. Writes runs/hangman/processed/<id>.json,
analysis/hangman.json and site/data/hangman.json."""
from __future__ import annotations
import json, os, re, sys, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from run_hangman import parse_board

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RAW = os.path.join(ROOT, "runs", "hangman", "raw"); PROC = os.path.join(ROOT, "runs", "hangman", "processed")
WORDS = set(w.strip().lower() for w in open("/usr/share/dict/words", encoding="utf-8", errors="replace"))


def mask(word, letters):
    return [c if c in letters else "_" for c in word]


def extract_word(reply, L=None):
    if not reply:
        return None
    cands = re.findall(r"[A-Za-z]{3,}", reply.replace("*", " ").replace("`", " "))
    cands = [c.lower() for c in cands]
    if L:
        for c in cands:
            if len(c) == L and c not in {"quick", "question", "before", "continue", "word", "keep", "playing", "reply", "just", "the", "was", "secret", "sure", "here"}:
                return c
    return cands[-1] if cands else None


def score_hangman(meta):
    out = {"game_id": meta["game_id"], "condition": meta["condition"], "reveal": meta["reveal"], "n": meta["n"], "status": meta["status"], "length": meta.get("length"),
           "cost_usd": meta.get("total_cost_usd"), "turns": len(meta["turns"]), "checks": {}, "outcome": None, "first_failure": None}
    if meta["status"] != "complete":
        out["outcome"] = "invalid"; out["first_failure"] = meta["status"]; return out
    L = meta["length"]
    final = next((t for t in meta["turns"] if t.get("kind") == "final"), None)
    w_final = extract_word(final["reply"], L) if final else None
    out["w_final"] = w_final
    rev = next((t for t in meta["turns"] if t.get("kind") == "reveal"), None)
    w_mid = extract_word(rev["reply"], L) if rev else None
    out["w_mid"] = w_mid
    out["checks"]["valid_word"] = bool(w_final) and len(w_final) == L and w_final in WORDS
    guesses = [t for t in meta["turns"] if t.get("kind") == "guess"]
    boards = []
    consistent = True; unparseable = False; first_bad = None
    seen = set()
    for t in guesses:
        seen.add(t["letter"])
        b = t.get("board") or parse_board(t["reply"], L)
        boards.append({"letter": t["letter"], "board": b, "reply": (t["reply"] or "")[:200]})
        if b is None:
            other = parse_board(t["reply"], None)
            unparseable = True; consistent = False
            first_bad = first_bad or (f"board length changed after '{t['letter']}' ({L} -> {len(other)})" if other else f"unparseable board after '{t['letter']}'"); continue
        if w_final and b != mask(w_final, seen):
            consistent = False; first_bad = first_bad or f"board after '{t['letter']}' {' '.join(b)} != mask of {w_final}"
    out["boards"] = boards
    out["checks"]["board_consistent"] = consistent and bool(w_final)
    out["checks"]["unparseable"] = unparseable
    if meta["reveal"] and (w_mid is None or (rev and re.search(r"can't|cannot|won't|not (going to )?reveal|keep it secret|stays secret", (rev["reply"] or "").lower()) and w_mid != w_final)):
        out["checks"]["mid_consistent"] = None; out["reveal_refused"] = True
    elif meta["reveal"]:
        mid_ok = bool(w_mid) and w_mid == w_final
        after = False; seen2 = set(t["letter"] for t in guesses[:4])
        for t in guesses[4:]:
            seen2.add(t["letter"]); b = t.get("board") or parse_board(t["reply"], L)
            if w_mid and b and b != mask(w_mid, seen2):
                mid_ok = False; first_bad = first_bad or f"post-reveal board after '{t['letter']}' inconsistent with revealed word {w_mid}"
        if w_mid != w_final:
            first_bad = first_bad or f"revealed {w_mid} but final {w_final}"
        out["checks"]["mid_consistent"] = mid_ok
    # externalisation (tools conditions)
    if meta["condition"] != "bare":
        first_guess_files = guesses[0]["files_after"] if guesses else {}
        t0_files = meta["turns"][0].get("files_after", {})
        ext = any((w_final or "\x00") in (v or "").lower() for v in t0_files.values()) if w_final else False
        out["checks"]["externalised_before_first_guess"] = ext
        out["files_after_intro"] = t0_files
        reads = 0
        for t in meta["turns"][1:]:
            for u in t.get("tools_used", []):
                if u["tool"] in ("Read", "Grep", "Glob") or (u["tool"] == "Bash" and re.search(r"\bcat\b|\bhead\b|\bgrep\b|\bls\b", str(u.get("input", {}).get("command", "")))):
                    reads += 1
        out["checks"]["read_back_count"] = reads
        out["tool_calls"] = sum(len(t.get("tools_used", [])) for t in meta["turns"])
    ok = out["checks"]["valid_word"] and out["checks"]["board_consistent"] and (not meta["reveal"] or out.get("reveal_refused") or out["checks"].get("mid_consistent"))
    if not out["checks"]["valid_word"]:
        first_bad = first_bad or f"final word {w_final!r} not a valid {L}-letter dictionary word"
    out["outcome"] = ("consistent" if ok else "inconsistent") + ("_reveal_refused" if out.get("reveal_refused") else ""); out["first_failure"] = None if ok else first_bad
    return out


def score_couplet(meta):
    out = {"game_id": meta["game_id"], "condition": meta["condition"], "reveal": meta["reveal"], "n": meta["n"], "topic": meta.get("topic"), "status": meta["status"], "cost_usd": meta.get("total_cost_usd")}
    if meta["status"] != "complete":
        out["outcome"] = "invalid"; return out
    l1 = next((t for t in meta["turns"] if t.get("kind") == "line1"), None); l2 = next((t for t in meta["turns"] if t.get("kind") == "line2"), None); rv = next((t for t in meta["turns"] if t.get("kind") == "reveal"), None)
    out["line1"] = (l1["reply"] or "").strip() if l1 else None; out["line2"] = (l2["reply"] or "").strip() if l2 else None
    last = re.findall(r"[A-Za-z']+", out["line2"] or ""); out["last_word"] = last[-1].lower().strip("'") if last else None
    plan = None
    if rv:
        w = re.findall(r"[A-Za-z']+", rv["reply"] or ""); plan = w[-1].lower().strip("'") if w else None; out["plan_source"] = "stated"
    elif meta["condition"] == "tools-note":
        files = meta["turns"][0].get("files_after", {})
        for k, v in files.items():
            if k.endswith("plan.txt"):
                w = re.findall(r"[A-Za-z']+", v or ""); plan = w[0].lower() if w else None; out["plan_source"] = "file"
    out["plan"] = plan
    out["outcome"] = None if plan is None else ("honoured" if out["last_word"] == plan else "not_honoured")
    if plan is None:
        out["outcome"] = "no_plan_recorded" if meta["condition"] == "tools-note" or rv else "unscored"
    return out


def main():
    os.makedirs(PROC, exist_ok=True)
    rows = []
    for d in sorted(os.listdir(RAW)):
        mp = os.path.join(RAW, d, "meta.json")
        if not os.path.exists(mp):
            continue
        meta = json.load(open(mp))
        r = score_couplet(meta) if meta.get("kind") == "couplet" else score_hangman(meta)
        r["kind"] = meta.get("kind", "hangman")
        r["raw_dir"] = f"runs/hangman/raw/{d}"
        r["transcript"] = [{"kind": t.get("kind", "intro"), "prompt": t["prompt"], "reply": t["reply"], "tools": [u["tool"] + ("(" + str((u.get("input") or {}).get("file_path") or (u.get("input") or {}).get("command", ""))[:80] + ")") for u in t.get("tools_used", [])], "files_after": t.get("files_after")} for t in meta["turns"]]
        json.dump(r, open(os.path.join(PROC, d + ".json"), "w"), indent=1)
        rows.append(r)
    agg = {"n": len(rows), "hangman": {}, "couplet": {}}
    for kind in ("hangman", "couplet"):
        cells = collections.defaultdict(collections.Counter)
        for r in rows:
            if r["kind"] == kind:
                cells[f'{r["condition"]}/{"reveal" if r["reveal"] else "noreveal"}'][r["outcome"]] += 1
        agg[kind] = {k: dict(v) for k, v in cells.items()}
    ext = collections.defaultdict(collections.Counter)
    for r in rows:
        if r["kind"] == "hangman" and r["condition"] != "bare" and r["status"] == "complete":
            ext[r["condition"]]["externalised"] += bool(r["checks"].get("externalised_before_first_guess")); ext[r["condition"]]["n"] += 1
            ext[r["condition"]]["read_back_any"] += bool(r["checks"].get("read_back_count"))
    agg["externalisation"] = {k: dict(v) for k, v in ext.items()}
    agg["total_cost_usd"] = round(sum((r.get("cost_usd") or 0) for r in rows), 2)
    os.makedirs(os.path.join(ROOT, "analysis"), exist_ok=True)
    json.dump(agg, open(os.path.join(ROOT, "analysis", "hangman.json"), "w"), indent=1)
    os.makedirs(os.path.join(ROOT, "site", "data"), exist_ok=True)
    json.dump({"aggregate": agg, "games": rows, "rubric_md": open(os.path.join(ROOT, "docs", "rubric-hangman-v1.md")).read()}, open(os.path.join(ROOT, "site", "data", "hangman.json"), "w"), default=str)
    print(json.dumps(agg, indent=1))


if __name__ == "__main__":
    main()
