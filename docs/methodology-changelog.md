# Methodology changelog

Every change to the protocol, rubric, detectors, tasks or scoring code made **after** the first
experimental run is listed here with the reason and the effect on results. Entries are
append-only.

| Date (UTC) | Change | Reason | Effect on results |
|---|---|---|---|
| 2026-09-18 | Rubric v1 frozen (`docs/rubric-v1.md`) before the first run. | — | — |
| 2026-09-18 (pre-run) | Validator subagents wrote reference A/B solutions for all 10 tasks and ran tests + detectors. Fixed: renderers test_t1/test_t2 `available_formats` equality (impossible from T3 on); ratelimit test_t1 called `allow` inside the window (token bucket could not pass) and test_t3 prune boundary ambiguity (50.0 → 57.0); detectors for ledger (dict/per-account logs), expr (table naming), renderers (`render_many` counted as a format function), graph (flat list / bitmask matrices), undo (bytes snapshots); eventbus detector emits `hybrid` for the auto-drained-queue design; prompt wording made more symmetric (kvstore tempt_A `instr` instead of `LIKE`; renderers/undo/expr evidence prompts strengthened on the weaker side; graph tempt_B now references `remove_node`; ledger evidence_B trimmed); a test comment in graph and a test name in ledger that used approach vocabulary were reworded. | Pre-run validation; no experimental data existed. | None (no runs yet). Rubric v1 gained the `hybrid` clause. |
