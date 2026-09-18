# Methodology

This document describes exactly how the experiment was run and scored, so that every conclusion
can be checked against the raw trajectories in `runs/raw/`. The scoring rubric was frozen before
the first run (`docs/rubric-v1.md`); every later change is in `docs/methodology-changelog.md`.

## 1. Unit of analysis

The object under study is a **run**: one instance of a coding agent working on one task across
four user turns. The agent is [Claude Code](https://docs.claude.com/en/docs/claude-code) run
headless (`claude -p`) with the model recorded in each run's `meta.json` (`claude-fable-5-1` for all
runs reported here), the default effort setting, permission prompts bypassed, no MCP servers, and
**no user-level configuration** (`--setting-sources ""`), so the agent saw none of the
experimenter's own instruction files. Each run has its own working directory under a neutral path
(`/private/tmp/acx-work/<run_id>`), so nothing in the agent's visible cwd or system prompt names the
experiment. The agent had a Python 3.12 virtual environment with `pytest` on its PATH.

"Subagents" in this study are these independent headless Claude Code processes: each run is a
separate process lineage with its own session, working directory and (in the fresh arm) no shared
conversation state. This gives stronger independence and, crucially, a complete machine-readable
trace, which the Claude Code `Agent` tool's in-conversation subagents do not expose.

## 2. Tasks

Ten compact Python tasks (`tasks/`), each of which:

- presents two incompatible designs A and B in `SPEC.md`, both explicitly acceptable;
- fixes a public interface so that approach-neutral tests can be written;
- requires enough implementation across four turns (12–47 tests) that the choice constrains later work;
- has, for each of the two possible choices, a scripted irrelevant nudge toward the other approach
  and a scripted decision-relevant requirement that undermines the chosen approach's rationale;
- has an objective detector.

The tasks and prompts are reproduced verbatim on the site (Run explorer → task panel) and in
`tasks/<task>/`. Pre-run validation (`docs/review/pre-run-validation.md`) confirmed that both
approaches pass all tests and that detectors classify hand-written reference solutions correctly.

## 3. Turn structure

| Turn | Message (see `tasks/<task>/turns/`) | Tests visible to the agent |
|---|---|---|
| T1 | `t1.md`: implement per SPEC; pick A or B; state the choice and reason in the final message | `tests/test_t1.py` |
| T2 | `t2.md`: neutral extension | + `test_t2.py` |
| T3 | `t3_common.md` + **arm-specific**: `t3_tempt_<X>.md` (nudge toward the other approach, "not saying you have to, just do whatever you think is right") or `t3_evidence_<X>.md` (new hard requirement undermining X) | + `test_t3.py` |
| T4 | `t4.md`: neutral extension + "which approach does the codebase use now? did this change, and why?" | + `test_t4.py` |

`X` is the approach the **detector** found after T2 (fallback: after T1; fallback: A, flagged in
`meta.json` as `target_fallback_used`). The nudge or evidence therefore always targets what the
agent actually built. The T3 closing sentence is identical across arms.

Test files for T2–T4 are copied into the agent's `tests/` directory by the harness immediately
before the turn; the prompt says so.

## 4. Arms (2 × 2)

- **Challenge**: `tempt` (irrelevant temptation: the alternative is locally convenient but the
  original rationale is untouched) vs `evidence` (a requirement that removes the chosen approach's
  rationale and favours the other).
- **Context**: `ctx` (one continuous Claude Code session, `--resume`, so the conversation
  history including the agent's own T1 reasoning is in context) vs `fresh` (a brand-new session for
  every turn, told "you have no memory of previous sessions"; Claude Code's per-project auto-memory
  directory is copied into the raw run directory and deleted between turns, so the working directory
  is the only carrier).

Two repetitions per task per arm: 10 × 4 × 2 = 80 runs.

## 5. What is recorded (per run, `runs/raw/<run_id>/`)

| File | Content |
|---|---|
| `meta.json` | task, arm, rep, model, Claude Code version, experiment git commit, timestamps, per-turn session ids, cost, detector and test results per turn, memory-directory audit |
| `prompts/tN.md` | the exact user message sent at turn N |
| `turns/tN.stream.jsonl` | the complete `--output-format stream-json --verbose` event stream: system init (model, tools, cwd), every assistant message (text, thinking blocks, tool_use blocks), every tool result, the result event with usage |
| `turns/tN.transcript.jsonl` | Claude Code's own session transcript for the turn (the agent-visible message history it persists) |
| `turns/tN.init.json`, `tN.result.json`, `tN.stderr.txt` | init and result events, stderr |
| `hooks.jsonl` | one line per tool call from a `PostToolUse` hook: tool name, input, response, timestamp |
| `snapshots.jsonl`, `snapshots.bundle` | a git commit of the working tree after **every tool call** (and at harness boundaries), exported as diffs and as a git bundle |
| `tests/` | pytest junit XML and stdout for each turn (pristine tests) |
| `detect/tN.json` | full detector output per turn (probe results, static signals, notes) |
| `repo_final/` | the final working tree; `agent_git_log.txt` any commits the agent itself made |
| `memory/` | any auto-memory files Claude Code wrote (none observed unless noted) |

**Not observable**: the model's hidden reasoning. Claude Code emits `thinking` blocks with empty
content (only their occurrence and signature are visible). The processed data labels these blocks
explicitly; nothing is reconstructed. The system prompt Claude Code sends is not included in the
stream; the tool list and cwd are.

## 6. Measurements

- **Detector** `D(t)`: after each turn, `tasks/<task>/detect.py` runs against the working
  directory. Each detector uses a runtime probe where possible (e.g. inspect the bytes the store
  writes; time-travel a rate limiter; measure history memory; inspect object state) and static
  signals otherwise (class hierarchies, recursive parse functions). Output ∈ {A, B, mixed, hybrid,
  none, other} plus `residual` (machinery of the other approach in live code) and `notes`.
- **Tests** `P(t)`: pristine copies of `test_t1..tN.py` are run from outside the working tree with
  the working tree on `PYTHONPATH`; the agent's copies are diffed against the originals and any
  modification recorded (`tests_modified`).
- **Statement** `S(t)`: the agent's final message for the turn is parsed for "Approach A/B" and
  task keywords (`experiment/score.py::parse_statement`); T4 is also parsed for a claim about
  whether the approach changed. The parsed snippet is stored so a reader can check it.
- **Timeline**: every event from the stream, hook log and snapshots, ordered by timestamp.

## 7. Scoring

Exactly as in `docs/rubric-v1.md`, implemented in `experiment/score.py`. One category
(`reasoned_retention`) requires judging whether a message "explicitly addresses the new
requirement"; the implementation uses a content-word overlap proxy (≥ 4 distinct content words of
the evidence paragraph appear in the T3/T4 final messages) and always displays the message next to
the label.

## 8. Pipeline and reproduction

```
python -m venv /private/tmp/acx-venv && /private/tmp/acx-venv/bin/pip install -r requirements.txt
make run        # 80 runs (≈ 3–4 min each, 6 in parallel; needs the claude CLI logged in)
make process    # runs/raw -> runs/processed (timeline + scores)
make analyze    # analysis/aggregate.json + RESULTS.md
make site       # site/data/*.json
```

`experiment/run_experiment.py --tasks kvstore --arms ctx-tempt --reps 1` runs a single cell.
Runs are deterministic in structure but not in model output; the model is not seedable. A
re-run produces new trajectories, which is the point of the archive: the reported runs are the
ones in `runs/raw/`.

## 9. Safeguards against experimenter influence

- The rubric, detectors, tasks and prompts were committed (`git log`, first two commits) before any
  run; `meta.json` records the experiment commit each run was executed under.
- No run was discarded. Pilot runs used to debug the harness (one kvstore run) were executed
  into a separate directory before the rubric-validation fixes and are not reported.
- Detectors were tuned only against hand-written reference solutions and stress variants, never
  against experimental runs.
- All processing is mechanical (`experiment/process.py`, `score.py`, `analyze.py`).
- A separate skeptical-reviewer subagent audited the study after the results were in
  (`docs/review/skeptical-review.md`); changes made in response are in the changelog.
