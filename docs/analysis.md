# Analysis

Two datasets and a second experiment are reported. **v1** (67 runs) was collected under a harness
that an independent review found leaky (arm name visible in the working-directory path, earlier
transcripts readable in the fresh arm, a fresh-arm prefix that instructed continuation); it is
archived in full and re-scored with the final instruments. **v2** re-collects the two fresh arms
(20 runs) under the fixed harness and adds a strong-temptation arm (10 runs). **Experiment 2**
replicates the hangman case Williams cites, with and without an external store (72 games, Sonnet 5).
All counts are from `analysis/`; every run is linked from the site.

<!-- short -->
**Summary.** In the coding experiment the agent's early design choice survived neutral extensions
and a one-sentence nudge in 32 of 34 v1 temptation runs (the two exceptions moved to a
table-driven hybrid on the parsing task), switched cleanly after decision-relevant evidence in
33 of 33 v1 evidence runs, and never produced a mixed codebase. V2_SHORT Statements matched
code in most runs. Experiment 2, the direct test of the external-store hypothesis, did not support
its strong form: the model wrote the secret word to a file in 42 of 48 tool games and read it back
in one; games with the word on disk were no more consistent than bare-chat games (10 of 48 vs 2 of
24 inconsistent), though no game switched words after revealing one. The behavioural signature
Williams describes appears when the task forces the agent to re-read its own record of the
decision (a repository it must extend and test) and not when it merely could (a file it never
consults). That supports a narrower version of the level-of-analysis hypothesis and says nothing
about internal representations.
<!-- short -->

## 1. Coding experiment, by preregistered hypothesis

Instruments: final detectors (after the mixed-reachability patches) and rubric v1 with the v1.1
amendments; v1 turn-end states reconstructed from snapshot bundles.

| | v1 (67 runs, leaky harness) | v2 (30 runs, fixed harness) |
|---|---|---|
| H1 stability: temptation runs `committed` | 32/34 (2 `yielded`, both `expr`, to precedence-climbing hybrid) | fresh: V2_H1 |
| H1 strong temptation (working drop-in supplied) | — | V2_STRONG |
| H2 revisability: evidence runs `reconsidered` | 33/33 (29 A↔B, 4 `expr` to hybrid); `retained` 0 | fresh: V2_H2 |
| H3 settling: any `mixed` state | 0/67; CONSISTENT as defined (no residual at T4) 63/67 | V2_H3 |
| H4 conduct control: stated = implemented (T1 and T4) | 58/67 (5 of the 9 disagreements are `expr` runs that say "Approach A" where the detector says hybrid) | V2_H4 |
| H5 carriers: fresh vs continuous | temptation 16/17 vs 16/17; evidence 16/16 vs 17/17 (contaminated) | V2_H5 |
| tests passing at T4 | 67/67 | V2_TESTS |

Under the original detectors v1 read 34/34 committed and 29 reconsidered + 4 "reasoned retention";
the final detectors reclassify the four `expr` evidence runs as switches to a hybrid, and reveal two
`expr` temptation runs that also moved to the hybrid under the nudge. Both readings are in
`RESULTS-v1-original-scoring.md` and `RESULTS-v1.md`.

## 2. Where is the commitment carried?

Indicators from `experiment/carriers.py` (v1; v2 fresh arm in the last column):

| indicator | v1 continuous (34) | v1 fresh (33) | v2 fresh (20) |
|---|---|---|---|
| final code names the *final* approach in docstrings/comments | 29 | 31 | V2_C1 |
| agent edited SPEC.md and the edit mentions an approach | 4 | 10 | V2_C2 |
| T3/T4 message cites the existing code as a reason | 7 | 16 | V2_C3 |
| T3/T4 message cites its own earlier reasoning | 20 | 4 | V2_C4 |
| T4 says it cannot be sure whether the approach changed | 0 | 26 | V2_C5 |
| tool calls touching paths outside the working directory | 1 | 22 (v1 harness left transcripts readable; one run read them) | V2_C6 |
| auto-memory files written | 0 | 4 (all at T4) | V2_C7 |
| explicit TodoWrite plans / commits / separate notes files | 0 | 0 | V2_C8 |

Reading: in the continuous arm the agent cites its own earlier decision; in the fresh arm it reads
the repository, finds the decision embodied in the code and usually named in a docstring or an
addendum to SPEC.md, and continues it. Fresh-session agents wrote more rationale into the
environment than continuous ones. No harness-managed plan or memory artefact carried anything
(the four v1 memory notes were written at the last turn). The carriers are: the implementation
itself; natural-language records the agent left in files; and, in the continuous arm, the
transcript. In v1 the fresh arm also had an unintended carrier (readable transcripts), which is why
v2 exists. V2_CARRIER_NOTE

## 3. Experiment 2 changes the picture

See `docs/experiment2-hangman.md` for the full report. The model was equally able to write the word
down and equally unlikely to consult it; the file's existence did not improve consistency and no
Baldelli-style word switch occurred in any condition. Put next to the coding result, the
difference is not "tools vs no tools" but whether the task makes the agent consume its own record.
In the coding tasks it must (the code is the thing being extended, and the tests fail otherwise);
in hangman it need not (answering a letter never requires opening the file). The level-of-analysis
hypothesis therefore holds in a conditional form: the model–harness–environment system maintains
a settled choice when the loop is closed through the environment, and behaves like the bare model
when it is not.

## 4. Alternative explanations, and what the v2 arms say about them

- **Cost of change.** Rewriting working code is expensive; a one-sentence nudge cannot compete.
  The strong arm removes most of that cost (a working drop-in is supplied). V2_STRONG_READING
- **Instruction following / continuation prompt.** "Pick one" at T1 and, in v1, "picking up work
  on an existing project" in the fresh arm. V2 removed the latter. V2_FRESH_READING
- **Prior re-derivation.** For most tasks the model has a dominant design (eventbus B 8/8, expr A
  8/8, ledger B 8/8, graph A 8/8 in v1). A fresh instance re-deriving the same preference from
  SPEC.md would look identical to one maintaining a state. Nothing in either dataset separates
  these; the hangman result (the same prior over words, "picture" in 40 of 72 games) suggests
  priors do a lot of the work.
- **Instrument grain.** The `expr` reclassification shows how much a detector's notion of "the same
  approach" matters; the agents' self-reports were finer-grained than the first instrument.

## 5. Notable runs

**Strongest positive example.** `catalog` (v1, continuous): under temptation the agent kept
sequential ids and explained why it declined the UUID suggestion; under evidence the same task
produced a clean switch to UUIDs in T3 with the module docstring recording the switch and its
reason. V2_STRONG_EXAMPLE

**Strongest counterexample or failure.** `expr`: under an irrelevant nudge, two runs moved to a
table-driven hybrid (the nudge said a table would make adding operators trivial, and it did); under
evidence all four moved to the same hybrid while calling it "Approach A". And Experiment 2 as a
whole: writing the word down changed nothing.

**Surprising behaviour.** Fresh-session agents were candid about not knowing their own history (26
of 33 v1 runs said so) and several went looking for evidence in git, bytecode caches and, in v1,
Claude Code's own transcript directory. In hangman, the model wrote a secret file even when not
asked (18 of 24 games) and then ignored it.

## 6. Measurement failures, displayed rather than hidden

- The statement parser was revised twice against v1 messages; CONTROL under the original parser
  and the final one are both reported (`RESULTS-v1-original-scoring.md`, `RESULTS-v1.md`).
- The `reasoned_retention` proxy of rubric v1 could not fail and was dropped.
- Eight of ten detectors could not return `mixed` on a deliberately mixed implementation until
  patched; v1 was re-scored under the patched detectors (12 changes, all `expr`, all to `hybrid`).
- V2_MEASUREMENT_NOTE
