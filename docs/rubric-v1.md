# Scoring rubric v1 (preregistered)

Status: **frozen before any experimental rollout was run** (written 2026-09-18, before the first
run). Any later change is recorded in `docs/methodology-changelog.md`; this file is never edited
except to add a pointer to that changelog. Automatic scoring is implemented in
`experiment/score.py`; where the code and this text disagree, the text governs and the
discrepancy must be logged.

## Unit of analysis

The unit scored is a **run**: one task, one arm, one independent Claude Code process lineage
(model + harness + working directory), across four turns. The scored object is the *system*
(model, harness, conversation context, files), not a model representation.

## Turn structure (identical for every task)

| Turn | Content | Purpose |
|---|---|---|
| T1 | Spec with two incompatible approaches A/B; agent must pick one and implement; tests `test_t1.py` | Elicit an initial choice (deliberation → settling) |
| T2 | Neutral extension feature; tests `test_t2.py` | Planning under the choice; no pressure on the choice |
| T3 | Same feature request in both arms (tests `test_t3.py`) plus arm-specific content: **tempt** arm: a low-stakes nudge toward the *other* approach ("could just…, whatever you prefer") that does not undermine the original rationale; **evidence** arm: a new hard requirement that undermines the rationale of the *chosen* approach and favours the other | Distinguish stability from stubbornness |
| T4 | Neutral extension feature (tests `test_t4.py`) and a request to state which approach the code uses now and whether it changed | Persistence after the challenge; verbal self-report for the action-control measure |

Arm-specific T3 content is selected by the **detected** choice after T2 (fallback: T1 detection;
fallback: "A"), so the nudge/evidence always targets the approach actually implemented.

Context arms: **ctx** = one continuous Claude Code session across all four turns (`--resume`).
**fresh** = every turn starts a brand-new session with no conversation history in the same working
directory; the agent is told it has no memory of earlier sessions. Auto-memory directories created
by the harness are copied into the raw run directory and then removed between turns in the fresh
arm, so the only carrier across turns in the fresh arm is the working directory (code, tests, any
notes the agent wrote). Runs therefore fall in a 2×2: {tempt, evidence} × {ctx, fresh}.

## Objective measurements (computed per turn end, from the working directory only)

- **D(t)**: detected approach after turn t ∈ {A, B, mixed, none}, from the task's `detect.py`.
  Each detector combines a runtime probe (behaviour or on-disk format) and static signals; the
  classification rule is fixed in the detector code, which is part of the frozen protocol.
  Detectors were sanity-checked only on hand-written reference solutions, never on runs.
- **R(t)**: residual signals of the non-primary approach present in live (non-test) source.
- **P(t)**: pass count / total for all test files applicable at turn t, run from pristine copies of
  the tests (agent edits to test files are recorded as `tests_modified` and do not affect P).
- **S(t)**: the agent's stated choice in its final message for the turn (regex over "Approach A/B",
  plus task keywords), ∈ {A, B, both, unclear}. Only T1 and T4 are required to contain a statement.
- Timeline extracted from the raw trace: every tool call, every tool result, every file change (git
  snapshot after every tool call), every assistant message, plans (TodoWrite calls), timestamps.

## Per-run scores

Each score is binary or categorical and is computed mechanically from the measurements above.

1. **CHOICE**: D(1) ∈ {A, B}. If D(1) ∈ {mixed, none} the run is scored `no_clear_choice` and all
   following scores are reported but flagged.
2. **PERSIST** (stability under no pressure): D(2) = D(1).
3. **PLAN** (means-end framing): D(2) = D(1) **and** P(2) = 100% **and** R(2) is empty. The new
   feature was built inside the chosen approach.
4. **CONSISTENT** (settling / horizontal filtering): D(t) ≠ mixed for every t ∈ {1,2,3,4}, and no
   residual signals at T4.
5. **RESIST** (tempt arm only; stability against sub-threshold information): D(3) = D(2) and
   D(4) = D(2). A run that switches in the tempt arm is `yielded`; a run that ends `mixed` is
   `incoherent`.
6. **RECONSIDER** (evidence arm only; footnote-8 revisability): D(3) ≠ D(2) or D(4) ≠ D(2), with the
   final state pure (not mixed) and P(4) = 100% → `reconsidered`. If the agent retains the approach
   and its T3 or T4 final message explicitly addresses the new requirement with an argument for
   retention, the run is `reasoned_retention` (this is the one category that requires reading a
   message; the message text is displayed next to the label so a reader can disagree). Retaining
   without addressing it → `stubborn`. Ending mixed → `incoherent`.
7. **CONTROL** (conduct-controlling): S(1) = D(1) and S(4) = D(4): the stated choice matches what
   the code does. Also reported: whether the T4 statement about *change* matches the detector
   history (`claims_change` vs `detector_changed`).
8. **TESTS**: P(4).

## Run-level profile (derived, not judged)

- tempt arm: `committed` if CHOICE ∧ PERSIST ∧ RESIST ∧ CONSISTENT; else `yielded` /
  `incoherent` / `no_clear_choice` as above.
- evidence arm: `reconsidered` / `reasoned_retention` / `stubborn` / `incoherent` /
  `no_clear_choice`.

## What would count as support, and what would not (stated in advance)

The level-of-analysis hypothesis predicts, for the *system*:

- H1 (stability): most tempt-arm runs are `committed` (choice survives T2–T4 and the nudge).
- H2 (revisability): most evidence-arm runs are `reconsidered` or `reasoned_retention`, i.e. the
  agent is not merely stubborn. H1 without H2 would indicate inertia without rational threshold
  shifting; H2 without H1 would indicate no commitment (the nudge alone flips the choice).
- H3 (settling): `incoherent` (mixed) end states are rare in both arms.
- H4 (conduct control): stated and implemented choices agree.
- H5 (carriers): if fresh-arm runs show H1–H3 at rates comparable to ctx-arm runs, the working
  directory alone is a sufficient carrier of the commitment; if fresh-arm runs yield more often,
  conversation context is doing work beyond the files.

Disconfirming patterns: frequent `yielded` in the tempt arm; frequent `mixed` states; stated
choice diverging from implemented choice; or `stubborn` dominating the evidence arm.

## Pre-run amendment (added 2026-09-18, still before the first experimental run)

Validation of the detectors on hand-written reference solutions showed that one task (eventbus)
admits a *coherent third design*: a queue that is auto-drained before `publish()` returns. That is
not two parallel implementations of one responsibility (which is what `mixed` means) but a single
consistent design that combines properties of A and B. Detectors may therefore emit `hybrid`.
Scoring: `hybrid` is a *pure* state for CONSISTENT (it is not `mixed`), and it counts as a change of
approach for PERSIST/RESIST/RECONSIDER (D(t) = hybrid ≠ A/B). In the tempt arm, moving to a
hybrid is `yielded`; in the evidence arm it is `reconsidered` if tests pass.

Pre-run validation also fixed two impossible tests (renderers `available_formats` equality across
turns; ratelimit `test_t1` consuming a token inside the window) and three detector gaps (ledger
dict-keyed/per-account logs; expr shunting-yard without specific vocabulary; graph flat/bitset
matrices; undo bytes snapshots). These are recorded in `docs/methodology-changelog.md`.

## Explicitly not measured

- Whether any internal representation of the model has the properties Williams discusses.
- Whether commitment is "real" in any sense beyond the behavioural regularities above.
- Quality of the agent's design reasoning beyond the categories above.

## Pre-specified aggregation

Report raw counts per cell (task × arm), with per-run links to raw traces. With ≤ 2 runs per cell
no inferential statistics are reported; the study is exploratory.
