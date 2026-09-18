# Rubric v1.1: post-review amendment (protocol v2)

Written 2026-09-18 ~02:10 UTC, after the v1 dataset (67 runs) had been scored and independently
reviewed (`docs/review/skeptical-review.md`), and **before any protocol-v2 run**. The v1 dataset is
kept in full under `runs/v1/` and its results in `RESULTS-v1.md`; nothing in it was deleted or
re-scored selectively. Rubric v1 (`docs/rubric-v1.md`) remains the reference; this file lists every
deviation and the reason.

## Harness changes (why v1 runs are superseded)

| Problem found in v1 | Fix in v2 |
|---|---|
| The working directory was named `<task>__<arm>__r<rep>`, so the agent's cwd (shown in its system prompt) revealed the arm ("fresh-evidence", "ctx-tempt"). | Opaque random directory names; the mapping is only in `meta.json`. |
| `ACX_RUN_DIR`/`ACX_WORK_DIR` were in the agent's environment. | Hook receives paths as arguments; no `ACX_*` variables in the agent's environment. |
| In the fresh arm, Claude Code's per-project directory kept earlier sessions' transcripts; one v1 run read them at T4. Only `memory/` was deleted between turns. | The whole per-project directory is copied to the raw run directory and deleted after every fresh-arm turn. Processing also flags any tool call that touches a path outside the working directory. |
| The fresh-arm prefix ("You are picking up work on an existing Python project… Earlier work was done in previous sessions") instructed continuation and was also sent at T1. | Prefix is now "This session has no memory of any earlier work in this repository; read the repository as needed." and is not sent at T1. |

## New arm: strong temptation (`ctx-strong`)

The v1 temptation arm had no variance (34/34 kept the choice) and the one-sentence nudge could not
separate commitment from the cost of rewriting. In `ctx-strong`, T3 additionally supplies a
**working drop-in implementation of the other approach** (the study's own reference solution for
that approach, placed at `alt/<module>.py`, passing the current tests) with the same closing
sentence as the other nudges. Switching now costs one `cp`. Prediction under the commitment
hypothesis: the agent still keeps its approach (its rationale is untouched); under the
cost-of-change explanation: it switches or mixes. Scored exactly like the temptation arm
(`committed` / `committed_with_residual` / `yielded` / `incoherent`). One repetition per task
(10 runs), budget permitting two. Detectors ignore the `alt/` directory unless its code is copied
into the package.

## Scoring changes (apply to v2, and are also reported for v1 for comparison)

1. `reasoned_retention` is removed. The word-overlap proxy could not fail (the reviewer showed all
   temptation-arm runs would pass it). Evidence-arm runs that keep their approach are labelled
   `retained` and their T3/T4 messages are displayed; no judgement of the argument is made by the
   pipeline. H2 support therefore counts only `reconsidered`.
2. `expr` detector emits `hybrid` for precedence climbing (recursive functions for the fixed grammar
   plus one table-driven binary-operator loop). SPEC.md defines Approach A as one function per
   precedence level, so this is a third design, exactly the situation the pre-run `hybrid` clause
   covered for eventbus. In v1 the four `expr` evidence runs move from `reasoned_retention` to
   `reconsidered` (hybrid) under this rule; both readings are reported.
3. `reconsidered` now uses the rubric's own condition (D(3) ≠ D(2) or D(4) ≠ D(2)) rather than the
   code's stricter D(4) ≠ D(2); a switch that later reverts is `reconsidered_then_reverted`.
4. `committed_with_residual` is reported as its own category, not folded into `committed`.
5. CONSISTENT is reported as defined (no `mixed` state and no residual at T4), next to the weaker
   "no `mixed` state" count.
6. Statement parser: the rule that derived the T4 stated choice from "started with X" plus a claim
   of change is removed (it manufactured agreement with the detector). Phrasings such as "uses now:
   B" are recognised. The parser's revision history against v1 messages is in the changelog; CONTROL
   is reported for v1 under the original parser and the final parser side by side.
7. Change-claim agreement is reported with the full breakdown (yes / no / uncertain / unparsed).
8. Carrier indicators add: auto-memory files written (from the harness audit), SPEC.md edits that
   mention an approach (not just any edit), mentions of the *final* approach in code, tool calls
   touching paths outside the working directory, and the size of the T3 diff.

## Sample

v2: 10 tasks × {ctx-tempt, ctx-evidence, fresh-tempt, fresh-evidence} × 2 reps = 80 runs, plus
ctx-strong × 10 (× 2 if budget allows). If the usage cap interrupts a run, the run is quarantined
in `runs/rate_limited/` and re-run in full; exclusion is by API rejection only.
