#!/usr/bin/env python3
"""One figure that states the result. Reads analysis/aggregate.json (v2), analysis/v1/aggregate.json and analysis/hangman.json."""
import json, os
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
v1 = json.load(open(os.path.join(ROOT, "analysis", "v1", "aggregate.json")))
v2 = json.load(open(os.path.join(ROOT, "analysis", "aggregate.json")))
H = json.load(open(os.path.join(ROOT, "analysis", "hangman.json")))
runs = v1["runs"] + v2["runs"]
tempt = [r for r in runs if r["arm"].endswith("tempt") or r["arm"].endswith("strong")]
evid = [r for r in runs if r["arm"].endswith("evidence")]
kept = sum(r["profile"] == "committed" for r in tempt); switched = sum(r["profile"] == "reconsidered" for r in evid)
mixed = sum("mixed" in (r["D"] or []) for r in runs)
fc = H["failure_classes_by_condition"]; ws = H["word_stability_reveal_games"]
word_n = sum(v["n"] for v in ws.values()); word_ok = sum(v["word_stable"] for v in ws.values())
def bad(k): c = fc[k]; return sum(v for kk, v in c.items() if kk != "none"), sum(c.values())
rows_h = [("no notepad (tools off)", *bad("bare")), ("notepad available, nothing said", *bad("tools-silent")), ("forced to read the notepad every turn", *bad("tools-consult"))]
W, F = 900, "font-family='-apple-system,Segoe UI,Helvetica,Arial,sans-serif'"
G, B, R, GR, INK, MU = "#2f855a", "#2b6cb0", "#c05621", "#d9d8d2", "#1c1c1a", "#6b6b66"
s = [f"<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 {W} 560' width='{W}' height='560' {F}><rect width='{W}' height='560' fill='#fff' rx='10'/>"]
def bar(y, label, k, n, col, text):
    s.append(f"<text x='30' y='{y+20}' font-size='15' fill='{INK}'>{label}</text>")
    s.append(f"<rect x='380' y='{y}' width='460' height='30' fill='{GR}' rx='4'/>")
    w = 460 * k / n if n else 0
    s.append(f"<rect x='380' y='{y}' width='{w:.1f}' height='30' fill='{col}' rx='4'/>")
    s.append(f"<text x='{390 if w > 120 else 380 + w + 8:.1f}' y='{y+21}' font-size='15' font-weight='700' fill='{'#fff' if w > 120 else INK}'>{text}</text>")
s.append(f"<text x='30' y='42' font-size='22' font-weight='700' fill='{INK}'>Did the agent stick to its decisions?</text>")
s.append(f"<text x='30' y='84' font-size='17' font-weight='700' fill='{INK}'>Coding agent (Claude Code), {len(runs)} runs, 10 tasks with a two-way design choice</text>")
bar(104, f"tempted to switch for no good reason ({len(tempt)} runs)", kept, len(tempt), G, f"{kept} of {len(tempt)} kept their choice")
bar(148, f"given a real reason to switch ({len(evid)} runs)", switched, len(evid), B, f"{switched} of {len(evid)} switched")
bar(192, f"ended up with both designs mixed together", mixed, len(runs), R, f"{mixed} of {len(runs)}")
s.append(f"<text x='30' y='250' font-size='13' fill='{MU}'>Includes runs where the agent's memory was wiped between rounds (it re-read its own code) and runs where a finished version of the other design was handed to it.</text>")
s.append(f"<text x='30' y='306' font-size='17' font-weight='700' fill='{INK}'>Hangman, the case Williams cites (Sonnet 5), {sum(sum(c.values()) for c in fc.values())} games</text>")
bar(326, f"changed its secret word after revealing it ({word_n} games checked)", word_n - word_ok, word_n, R, f"{word_n - word_ok} of {word_n}")
s.append(f"<text x='30' y='392' font-size='15' fill='{INK}'>games with at least one miscounted letter:</text>")
y = 404
for label, k, n in rows_h:
    bar(y, f"   {label}", k, n, R, f"{k} of {n}"); y += 40
s.append(f"<text x='30' y='{y+16}' font-size='13' fill='{MU}'>The word never changed; the letters got miscounted, and a notepad did not help with that.</text>")
s.append("</svg>")
open(os.path.join(ROOT, "site", "assets", "figures", "summary.svg"), "w").write("\n".join(s))
print("summary.svg", kept, len(tempt), switched, len(evid), mixed, word_ok, word_n, rows_h)
