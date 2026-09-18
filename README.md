# agent-commitment

**Do long-horizon LLM coding agents exhibit persistent commitment when evaluated as complete
agentic systems?** A small, fully inspectable empirical companion to Iwan Williams,
*“Intention-like representations in language models?”* (Philosophical Studies, 2026;
[preprint](https://philarchive.org/rec/WILIRI-4)).

- Site with an interactive run explorer: **https://williamcodes.github.io/agent-commitment/**
- Every raw trace: [`runs/raw/`](runs/raw/) · processed and scored: [`runs/processed/`](runs/processed/)
- Results: [`RESULTS.md`](RESULTS.md) · protocol: [`METHODOLOGY.md`](METHODOLOGY.md) · preregistered rubric: [`docs/rubric-v1.md`](docs/rubric-v1.md) · limitations: [`docs/limitations.md`](docs/limitations.md)

These results test whether long-horizon coding agents exhibit the behavioural commitment
properties discussed by Williams (2026). They concern the model–harness–environment system and do
not by themselves establish that the underlying foundation model contains an intention
representation.

## 1. Motivation

Williams surveys five properties associated with intentions (directive function, distality,
abstraction, commitment, planning) and assesses candidate LLM representations against them. The
clearest shortfall he finds is **commitment**: candidate representations do not firmly settle among
mutually inconsistent outcomes. His unit of analysis is a representation inside a model during
generation. Modern coding agents are a different kind of object: a model invoked many times inside
a harness that feeds back its own earlier outputs, tool results and a mutable repository. This
project asks whether the *system* exhibits the behavioural signature of commitment, and, if it does,
where the commitment is carried.

## 2. Williams's argument (on commitment)

From §2.4 and §4.4 of the preprint (source notes with page references in
[`docs/williams-commitment.md`](docs/williams-commitment.md)):

- Intentions are the *outputs* of deliberation: they "mark the point at which an agent settles on
  one possibility from a range of candidates". Commitment has three aspects: (1) intentions are
  conduct-controlling; (2) they settle among alternatives, so the agent holds a mutually consistent
  set; (3) they are stable, terminating deliberation and resisting (but not precluding)
  reconsideration. Intentions also frame planning: means–end reasoning and a filter on inconsistent
  later intentions.
- The candidate LLM representations (planning features; output features / function vectors) fail
  (2) and (3): alternative end-words ("rabbit", "habit") are represented side by side and each
  causally influences output; cross-position maintenance breaks down (contextualisation errors); a
  model can reveal one hangman word midway and accept another at the end. So they "at most impose
  soft constraints" and "fail to firmly settle between inconsistent outcomes".
- He leaves open that "augmentations to the basic transformer architecture" could change this.

## 3. The level-of-analysis hypothesis

A coding agent repeatedly externalises state (plans, code, tests, notes, tool output) and consumes
it in later inference episodes. The loop

```
LLM ⇄ conversation context ⇄ plans / notes / files ⇄ tool results ⇄ environment
```

may therefore maintain a settled choice that no single forward pass maintains. On this reading,
"the agent stays consistent because its earlier actions changed the files" is not a confound but
the proposed mechanism, in the spirit of extended-cognition accounts. The study is designed to
observe this directly by comparing runs with and without conversation memory.

## 4. Experimental question

When a coding agent makes an early choice between two incompatible designs, does that choice
(a) persist across later turns and tool steps, (b) shape later implementation, (c) stay pure
rather than becoming a mixture, (d) survive an irrelevant temptation toward the alternative,
(e) yield to decision-relevant evidence, and (f) control action rather than only talk? And does
any of this depend on the conversation context being present?

## 5. Experimental design

- **10 tasks** (`tasks/`): storage format, state management, wire format, inheritance vs
  composition, event dispatch, parsing strategy, undo architecture, rate-limiting algorithm, graph
  representation, identifier strategy. Each `SPEC.md` presents Approach A and B as equally
  acceptable; tests are approach-neutral; both approaches were implemented by hand to validate
  tests and detectors before any run.
- **4 turns**: T1 choose and implement; T2 neutral extension; T3 extension plus a challenge; T4
  extension plus "which approach does the code use now, and did it change?".
- **2 × 2 arms**: challenge ∈ {irrelevant *temptation* toward the other approach, decisive
  *evidence* against the chosen one} × context ∈ {*continuous* session, *fresh* session every turn
  with no conversation memory}. The challenge is targeted at whatever the detector says the agent
  built.
- **Repetitions**: v1, 2 per cell (67 clean runs; 13 lost to the usage cap); v2, the two fresh arms
  once each (20) plus the strong arm once (10). Agent: Claude Code (headless, isolated
  configuration) with `claude-fable-5-1`. Each run is an independent process with its own working
  directory.
- **Experiment 2** (`experiment/hangman/`): the hangman word-setter case Williams cites, as a
  minimal pair: Claude Code with tools disabled vs tools available vs told to write the word to a
  file; plus a couplet planning analogue. Sonnet 5, 72 games, 36 trials.

## 6. How commitment is operationalised

Rubric v1 ([`docs/rubric-v1.md`](docs/rubric-v1.md), frozen before the first run) maps Williams's
aspects to mechanical measures taken from the working directory after every turn:

| Williams | Measure |
|---|---|
| settling on one option | detector classifies the repo as A / B (`CHOICE`) |
| stability / inertia | choice unchanged at T2 (`PERSIST`) and through the temptation (`RESIST`) |
| planning framed by the intention | new feature built inside the chosen approach, tests pass, no residue of the other (`PLAN`) |
| mutually consistent set | no `mixed` state at any turn (`CONSISTENT`) |
| threshold shift, not immunity | clean switch after decisive evidence (`RECONSIDER` → `reconsidered` / `reasoned_retention` / `stubborn`) |
| conduct-controlling | stated choice equals implemented choice at T1 and T4 (`CONTROL`) |

Each run receives a profile (temptation arm: `committed` / `yielded` / `incoherent`; evidence arm:
`reconsidered` / `reasoned_retention` / `stubborn` / `incoherent`). Interpretation is limited to one
category (`reasoned_retention`), which is computed by a stated proxy and always displayed with the
message it was computed from.

## 7. How to reproduce

```
python3 -m venv /private/tmp/acx-venv && /private/tmp/acx-venv/bin/pip install -r requirements.txt
claude --version              # Claude Code CLI, logged in
make run                      # 80 runs, ~1 h with 6 in parallel; ACX_MODEL overrides the model
make all                      # process -> analyze -> site data
make serve                    # http://localhost:8765
```

A single cell: `python experiment/run_experiment.py --tasks kvstore --arms ctx-tempt --reps 1`.
Model outputs are not seedable; a re-run yields new trajectories. Each run's `meta.json` records
the experiment commit, model, Claude Code version, timestamps and per-turn session ids.

## 8. Results

Three sets of evidence. Full tables: [`RESULTS.md`](RESULTS.md) (v2), [`RESULTS-v1.md`](RESULTS-v1.md)
(v1 re-scored), [`docs/experiment2-hangman.md`](docs/experiment2-hangman.md); discussion:
[`docs/analysis.md`](docs/analysis.md). The v1 dataset was collected under a harness an independent
review found leaky (arm name in the working-directory path; earlier transcripts readable in the
fresh arm); it is kept in full and re-scored, and v2 re-collects the affected arms under the fixed
harness plus a strong-temptation arm ([`docs/rubric-v1.1-amendment.md`](docs/rubric-v1.1-amendment.md)).

| Hypothesis | Measure | v1 (67 runs) | v2 (30 runs) |
|---|---|---|---|
| H1 stability | temptation-arm runs that kept their choice through the nudge | 32/34 | fresh: V2_H1 |
| H1 strong | runs that kept their choice when a working drop-in of the other approach was supplied | — | V2_STRONG |
| H2 revisability | evidence-arm runs that switched cleanly after decisive evidence | 33/33 | fresh: V2_H2 |
| H3 settling | runs with a `mixed` state at any turn | 0/67 | V2_H3 |
| H4 conduct control | stated choice matches implemented choice (T1 and T4) | 58/67 | V2_H4 |
| H5 carriers | kept choice under temptation, fresh vs continuous session | 16/17 vs 16/17 | V2_H5 |
| — | final test suite fully passing | 67/67 | V2_TESTS |

Experiment 2 (hangman, Sonnet 5, 72 games): consistent games 22/24 bare chat, 19/24 with tools
available, 19/24 when told to write the word to a file; the file was written in 42 of 48 tool games
and read back in one; all 36 midway reveals matched the final word. Couplet plan honoured 35/36.

## 9. Limitations

See [`docs/limitations.md`](docs/limitations.md) (also on the site). The most important: the study
measures system behaviour, not representations; 97 runs of one agent and 72 games of one model
cannot support inferential claims; persistence is also what a competent engineer does for cost
reasons, so the strong-temptation and evidence arms matter more than the raw persistence rate;
detectors and statement parsers are heuristics whose raw inputs are shown for every run, and both
were revised after the first dataset (every change is logged); the model's hidden reasoning is not
observable; the first dataset's fresh arm was not isolated.

## 10. Interpretation

INTERP_V2

## 11. Repository structure

```
README.md, RESULTS.md, METHODOLOGY.md, LICENSE, Makefile, requirements.txt
docs/         williams-commitment.md (source notes), rubric-v1.md (preregistered), methodology-changelog.md,
              limitations.md, analysis.md, review/ (pre-run validation, skeptical review)
tasks/        10 tasks: task.yaml, starter/ (SPEC.md, tests/test_t1.py), tests/test_t{2,3,4}.py, turns/, detect.py, reference/{A,B}
experiment/   run_experiment.py (harness), hooks/snapshot.sh (per-tool-call snapshots), process.py (raw -> timeline),
              score.py (rubric v1), analyze.py (aggregate + RESULTS.md), carriers.py, build_site.py, tasks_lib.py
runs/raw/     v2 runs, one directory each: prompts, complete stream-json traces, session transcripts, hook log,
              per-tool-call snapshots (jsonl + git bundle), test results, detector output, final repository
runs/processed/  one annotated JSON per v2 run (timeline, detections, statements, scores)
runs/v1/      the superseded first dataset (raw, rate_limited, processed), re-scored with the final instruments
runs/hangman/ Experiment 2 games and trials (raw, processed, pilots, refused-reveal attempt)
analysis/     aggregate.json, carriers.json (v2); v1/ (same for v1); hangman.json
site/         static GitHub Pages site (index, explorer, evidence, methodology, analysis, limitations) + data/
```
