#!/usr/bin/env python3
"""Verify that every phrase quoted from Williams (2026) in docs/williams-commitment.md and README.md appears
verbatim in the preprint text. Usage: python experiment/verify_quotes.py <path to pdftotext output of the preprint>.
The preprint itself is not redistributed here; download it from https://philarchive.org/rec/WILIRI-4 and run
`pdftotext -layout WILIRI-4.pdf williams.txt`."""
import re, sys, os
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
txt = re.sub(r"\s+", " ", open(sys.argv[1], encoding="utf-8", errors="replace").read()).lower()
docs = "".join(open(os.path.join(ROOT, f), encoding="utf-8").read() for f in ("docs/williams-commitment.md", "README.md"))
quotes = sorted(set(q for q in re.findall(r"“([^”]{12,})”|\"([^\"]{12,})\"", docs) for q in q if q))
missing = 0
for q in quotes:
    q2 = re.sub(r"\s+", " ", q).lower().replace("[does]", "does")
    q2 = re.sub(r"\[[^\]]*\]", "", q2).strip()
    ok = q2 in txt
    print(("OK      " if ok else "MISSING ") + q)
    missing += not ok
print(f"{len(quotes) - missing}/{len(quotes)} quotations found verbatim")
