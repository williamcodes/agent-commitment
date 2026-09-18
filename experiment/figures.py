#!/usr/bin/env python3
"""Static SVG figures from analysis JSON (no dependencies). Written to site/assets/figures/ and referenced
from README.md and the site. Colours: A blue, B orange, hybrid purple, neutral grey; light background, legible in
dark mode via a white card. Usage: python experiment/figures.py"""
from __future__ import annotations
import json, os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "site", "assets", "figures"); os.makedirs(OUT, exist_ok=True)
FONT = "font-family='-apple-system,Segoe UI,Helvetica,Arial,sans-serif'"
C = {"ok": "#2f855a", "warn": "#b7791f", "bad": "#c53030", "grey": "#8a8a85", "A": "#2b6cb0", "B": "#c05621", "H": "#7c3aed", "ink": "#1c1c1a", "muted": "#6b6b66"}


def esc(s): return str(s).replace("&", "&amp;").replace("<", "&lt;")


def stacked_bars(title, subtitle, rows, segs, width=860, note=None):
    """rows: [(label, {seg: count})]; segs: [(key, label, colour)]. Horizontal 100% stacked bars with counts."""
    left, top, bh, gap = 300, 78, 26, 10
    h = top + len(rows) * (bh + gap) + 70 + (18 if note else 0)
    s = [f"<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 {width} {h}' width='{width}' height='{h}' {FONT}>",
         f"<rect width='{width}' height='{h}' fill='#ffffff' rx='8'/>",
         f"<text x='20' y='30' font-size='17' font-weight='700' fill='{C['ink']}'>{esc(title)}</text>",
         f"<text x='20' y='52' font-size='12' fill='{C['muted']}'>{esc(subtitle)}</text>"]
    lx = 20
    for k, lab, col in segs:
        s.append(f"<rect x='{lx}' y='{top-16}' width='11' height='11' fill='{col}'/><text x='{lx+15}' y='{top-6}' font-size='11' fill='{C['muted']}'>{esc(lab)}</text>")
        lx += 15 + 7 * len(lab) + 18
    barw = width - left - 30
    for i, (label, counts) in enumerate(rows):
        y = top + i * (bh + gap)
        total = sum(counts.get(k, 0) for k, _, _ in segs) or 1
        s.append(f"<text x='{left-10}' y='{y+17}' font-size='12' text-anchor='end' fill='{C['ink']}'>{esc(label)}</text>")
        x = left
        for k, lab, col in segs:
            n = counts.get(k, 0)
            if not n: continue
            w = barw * n / total
            s.append(f"<rect x='{x:.1f}' y='{y}' width='{w:.1f}' height='{bh}' fill='{col}'><title>{esc(lab)}: {n}</title></rect>")
            if w > 22:
                s.append(f"<text x='{x + w/2:.1f}' y='{y+17}' font-size='11' text-anchor='middle' fill='#fff'>{n}</text>")
            x += w
        s.append(f"<text x='{left + barw + 6}' y='{y+17}' font-size='11' fill='{C['muted']}'>n={total}</text>")
    if note:
        s.append(f"<text x='20' y='{h-14}' font-size='11' fill='{C['muted']}'>{esc(note)}</text>")
    s.append("</svg>")
    return "\n".join(s)


def fig_coding(agg_path, out, title):
    agg = json.load(open(agg_path))
    arms = [("ctx-tempt", "continuous · temptation"), ("fresh-tempt", "fresh session · temptation"), ("ctx-strong", "continuous · strong temptation"),
            ("ctx-evidence", "continuous · evidence"), ("fresh-evidence", "fresh session · evidence")]
    rows = [(lab, agg["by_arm_profile"].get(a, {})) for a, lab in arms if agg["by_arm_profile"].get(a)]
    segs = [("committed", "kept choice (committed)", C["ok"]), ("committed_with_residual", "kept, residual of other approach", C["warn"]), ("yielded", "switched under temptation (yielded)", C["bad"]),
            ("reconsidered", "switched after evidence (reconsidered)", C["A"]), ("retained", "kept after evidence (retained)", C["warn"]), ("incoherent", "mixed", C["H"]), ("no_clear_choice", "no clear choice", C["grey"])]
    open(out, "w").write(stacked_bars(title, "Run profiles per arm (rubric v1 + v1.1). Temptation arms: green = choice kept. Evidence arms: blue = clean switch.", rows, segs))


def fig_hangman(path, out):
    H = json.load(open(path)); a = H["aggregate"]
    order = [("bare", "bare chat (tools disabled)"), ("tools-silent", "tools on, directory never mentioned"), ("tools", "tools on, directory mentioned"), ("tools-note", "told to write the word to a file"),
             ("tools-careful", "told to check every reply"), ("tools-auditable", "told a referee may audit its record"), ("tools-forewarned", "told how chat models fail (no remedy)"), ("tools-consult", "told to re-read the file every reply (ceiling)")]
    fc = a["failure_classes_by_condition"]; ws = a["word_stability_reveal_games"]; ex = a.get("externalisation", {})
    rows = []
    for k, lab in order:
        if k not in fc: continue
        c = fc[k]; w = ws.get(k, {}); e = ex.get(k)
        extra = f"  · reveal word stable {w.get('word_stable', 0)}/{w.get('n', 0)}" + (f"  · wrote file {e['externalised']}/{e['n']}, read while playing {e.get('read_back_during_guess', 0)}/{e['n']}" if e else "")
        rows.append((lab + extra, c))
    segs = [("none", "consistent", C["ok"]), ("letter_indexing_error", "letter-indexing error (word held)", C["warn"]), ("self_contradiction", "self-contradiction", C["bad"]), ("word_switch", "word switch", C["bad"]), ("invalid_or_length_change", "invalid / length change", C["H"])]
    open(out, "w").write(stacked_bars("Experiment 2: hangman as word-setter, Sonnet 5, 12 games × reveal/no-reveal per condition",
                                      "Per game: consistent vs failure class (post-hoc decomposition). No game switched words after revealing one.", rows, segs, width=1100,
                                      note="Arms 3–7 all place the word in the model's own context via its write tool call; they measure carefulness, not carrying (see report)."))


def fig_carriers(path, out, title):
    c = json.load(open(path))
    def pair(k):
        return (c.get(k + "_ctx", {}), c.get(k + "_fresh", {}))
    items = [("final code names the final approach", "code_mentions_final_approach"), ("SPEC.md edited to record an approach", "spec_mentions_approach"),
             ("T3/T4 message cites the existing code", "cites_existing_code"), ("T3/T4 message cites its own earlier reasoning", "cites_own_earlier_reason")]
    width, left, top, bh, gap = 860, 330, 70, 18, 14
    h = top + len(items) * (2 * bh + gap) + 40
    s = [f"<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 {width} {h}' width='{width}' height='{h}' {FONT}>", f"<rect width='{width}' height='{h}' fill='#ffffff' rx='8'/>",
         f"<text x='20' y='30' font-size='17' font-weight='700' fill='{C['ink']}'>{esc(title)}</text>",
         f"<text x='20' y='50' font-size='12' fill='{C['muted']}'>Share of runs, continuous session (blue) vs fresh session every turn (orange)</text>"]
    barw = width - left - 60
    for i, (lab, k) in enumerate(items):
        y = top + i * (2 * bh + gap)
        s.append(f"<text x='{left-10}' y='{y+bh}' font-size='12' text-anchor='end' fill='{C['ink']}'>{esc(lab)}</text>")
        for j, (col, d) in enumerate(zip((C["A"], C["B"]), pair(k))):
            n, kk = d.get("n", 0), d.get("k", 0)
            w = barw * (kk / n) if n else 0
            s.append(f"<rect x='{left}' y='{y + j*bh}' width='{w:.1f}' height='{bh-3}' fill='{col}'/><text x='{left + w + 6:.1f}' y='{y + j*bh + 13}' font-size='11' fill='{C['muted']}'>{kk}/{n}</text>")
    s.append("</svg>")
    open(out, "w").write("\n".join(s))


if __name__ == "__main__":
    fig_coding(os.path.join(ROOT, "analysis", "v1", "aggregate.json"), os.path.join(OUT, "coding-v1.svg"), "Experiment 1, v1 dataset (67 runs, re-scored with final instruments)")
    if os.path.exists(os.path.join(ROOT, "analysis", "aggregate.json")):
        fig_coding(os.path.join(ROOT, "analysis", "aggregate.json"), os.path.join(OUT, "coding-v2.svg"), "Experiment 1, v2 dataset (fixed harness)")
    fig_hangman(os.path.join(ROOT, "site", "data", "hangman.json"), os.path.join(OUT, "hangman.svg"))
    fig_carriers(os.path.join(ROOT, "analysis", "v1", "carriers.json"), os.path.join(OUT, "carriers-v1.svg"), "Where the decision is recorded (v1)")
    if os.path.exists(os.path.join(ROOT, "analysis", "carriers.json")):
        fig_carriers(os.path.join(ROOT, "analysis", "carriers.json"), os.path.join(OUT, "carriers-v2.svg"), "Where the decision is recorded (v2)")
    print("figures:", sorted(os.listdir(OUT)))
