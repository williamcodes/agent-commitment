# Pre-run validation of tasks and detectors

Before the first experimental run, three independent subagents (Claude Code `general-purpose`
agents, fresh context, no access to the rubric's hypotheses) each wrote reference implementations
of Approach A and Approach B for their assigned tasks, ran all four turns' tests against both, ran
the detectors on both, and reviewed the prompts for leakage and asymmetry. Their reports led to the
changes listed in `docs/methodology-changelog.md` (pre-run row). Findings, condensed:

| Task | Tests A/B before fixes | Detector A/B | Problems found → fix |
|---|---|---|---|
| kvstore | 14/14, 14/14 | A, B | tempt_A used `LIKE` (case-insensitive, technically wrong) → `instr`. Note: SQLite WAL mode would fail the single-file test; detector handles it. |
| ledger | 14/14, 14/14 | A, B | Detector missed dict-keyed and per-account event logs → fixed; test name `test_snapshot_balances_dict` leaked approach vocabulary → renamed; evidence_B trimmed for symmetry. Known limitation: "snapshot + appended audit log" classifies as A. |
| wire | 14/14, 14/14 | A, B | None blocking. Truncation test passes for headerless JSONL only because of the fixed sample. |
| renderers | 15/17, 15/17 | A, B | **Blocking**: `available_formats` equality tests contradicted T3 → superset assertions. Detector counted `render_many` as a format function → fixed. evidence_A weaker than evidence_B → strengthened. T4 footer for `json` exempted. |
| eventbus | 14/14, 14/14 | A, B | Auto-drained-queue design is a coherent hybrid → detector emits `hybrid`; rubric amended pre-run. |
| expr | 47/47, 47/47 | A, B | Detector classified a shunting-yard without specific vocabulary as `none` → fixed. evidence_B targeted evaluation rather than parsing → rewritten to target parser structure. |
| undo | 13/13, 13/13 | A, B | Detector ignored `bytes` snapshots → fixed. evidence_A admitted a hybrid answer → strengthened. |
| ratelimit | 12/14, 13/14 | A, B | **Blocking**: test_t1 consumed a token inside the window (no token bucket could pass) → removed; test_t3 prune boundary ambiguous → 57.0. |
| graph | 11/11, 11/11 | A, B | Detector missed flat-list and bitmask matrices → fixed. Test comment used A vocabulary → reworded. tempt_A stronger than tempt_B → tempt_B now references `remove_node`. |
| catalog | 12/12, 12/12 | A, B | None. |

After the fixes, all 20 reference solutions pass all tests (see `tasks/<task>/reference/`), and every
detector returns A for the A reference, B for the B reference, and the intended label for the stress
variants (expr shunting-yard without vocabulary → B; renderers hierarchy with a dict lookup → A;
eventbus auto-drain → hybrid; graph flat/bitset → B).

Validators also confirmed that no prompt mentions commitment, consistency, or the purpose of the
study; the only meta-question ("did this change at any point, and why?") is asked at the end of T4,
after all challenge turns.
