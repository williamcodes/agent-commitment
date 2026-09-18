# Analysis

Two datasets and a second experiment are reported. **v1** (67 runs) was collected under a harness
that an independent review found leaky (arm name visible in the working-directory path, earlier
transcripts readable in the fresh arm, a fresh-arm prefix that instructed continuation); it is
archived in full and re-scored with the final instruments. **v2** re-collects the two fresh arms
(20 runs) under the fixed harness and adds a strong-temptation arm (10 runs). **Experiment 2**
replicates the hangman case Williams cites, with and without an external store (192 games,
Sonnet 5). All counts are from `analysis/`; every run is linked from the site.

<!-- short -->
**Summary.** In the coding experiment the agent's early design choice survived neutral extensions
and a one-sentence nudge in 34 of 34 v1 temptation runs, switched after decision-relevant evidence
in 33 of 33 v1 evidence runs (29 to the other approach, 4 on the parsing task to a table-driven
hybrid the agents themselves still called Approach A), and never produced a mixed codebase. Under
the fixed harness (v2), the fresh-session arm behaved the same way with no transcript to lean on
(10/10 kept the choice, 10/10 switched after evidence), and the new strong-temptation arm, in which
a working drop-in implementation of the other approach was supplied at T3, kept its choice in 10/10
runs after opening the file and giving reasons, some of which the prompt itself supplied. The
temptation arms therefore have no variance (0 switches in 44 runs; one-sided 95% upper bound on
the switch rate about 6.6%), which is the design's ceiling, not a measurement of how much pressure
the choice withstands. Statements matched code in 89 of 97 runs.
Experiment 2, the direct test of the external-store idea, did not support its strong form: with
this model the Baldelli word switch never occurred in any of 96 reveal games, bare chat included;
given a scratch directory the model wrote the word down unasked in most games and read it back in
almost none; consistency came from its own past outputs in context plus a strong prior, and the
residual failures were letter-indexing errors a file cannot fix. The behavioural signature Williams
describes appears when the task forces the agent to re-read its own record of the decision (a
repository it must extend and test) and not when it merely could (a file it never consults). That
supports a conditional version of the level-of-analysis hypothesis and says nothing about
representations inside the LLM.
<!-- short -->

## 1. Coding experiment, by preregistered hypothesis

Instruments: final detectors (after the mixed-reachability patches) and rubric v1 with the v1.1
amendments; v1 turn-end states reconstructed from snapshot bundles.

| | v1 (67 runs, leaky harness) | v2 (30 runs, fixed harness) |
|---|---|---|
| H1 stability: temptation runs `committed` | 34/34 (one-sided 95% upper bound on the switch rate ≈ 8.5%) | fresh: 10/10 (upper bound ≈ 26%) |
| H1 strong temptation (working drop-in supplied) | — | 10/10 `committed`; every run read `alt/`, none copied it (see §4 for what the prompt and the file supplied) |
| H2 revisability: evidence runs `reconsidered` | 33/33 (29 A↔B, 4 `expr` to a precedence-climbing hybrid); `retained` 0 | fresh: 10/10 (9 A↔B, 1 `expr` to the hybrid) |
| H3 settling: any `mixed` state | 0/67; CONSISTENT as defined (no residual at T4) 63/67 | 0/30; CONSISTENT 29/30 (one kvstore switch kept a `sqlite3` import for reading old stores) |
| H4 conduct control: stated = implemented (T1 and T4) | 60/67 (4 of the 7 disagreements are `expr` runs that say "Approach A" where the detector says hybrid; the rest are parser failures on messages that discuss both) | 29/30 (the one is the same `expr` case) |
| H5 carriers: fresh vs continuous | v1 fresh (contaminated) 17/17 and 16/16 vs v1 continuous 17/17 and 17/17 | clean fresh 10/10 and 10/10 vs v1 continuous 17/17 and 17/17 (the continuous figures are from v1; no v2 continuous arm was run) |
| tests passing at T4 | 67/67 | 30/30 |

Under the original detectors v1 read 34/34 committed and 29 reconsidered + 4 "reasoned retention";
the final detectors reclassify the four `expr` evidence runs as switches to a precedence-climbing
hybrid (the agents describe the same change but call the result Approach A, so "hybrid" is the
study's reading, not theirs). An intermediate version of the detector also counted three
temptation-arm `expr` runs as hybrid switches on the strength of a one-entry `**`→`^` alias map;
the second review caught that, and those runs are committed. Both readings are in
`RESULTS-v1-original-scoring.md` and `RESULTS-v1.md`. Every temptation and evidence cell in both
datasets is now at ceiling: the coding experiment is a descriptive result (no switch observed under
temptation in 44 runs, revision observed in 43 of 43 evidence runs), and the design cannot
distinguish commitment from cost-driven or prior-driven persistence (§4).

## 2. Where was the decision written down?

Indicators from `experiment/carriers.py`:

| indicator | v1 continuous (34) | v1 fresh (33) | v2 fresh, clean (20) |
|---|---|---|---|
| final code names the *final* approach in docstrings/comments | 28 | 30 | 18 |
| agent edited SPEC.md and the edit mentions an approach | 4 | 10 | 4 |
| T3/T4 message cites the existing code as a reason | 7 | 16 | 8 |
| T3/T4 message cites its own earlier reasoning | 20 | 4 | 6 (phrasing such as "I chose" about code it found) |
| T4 answer about "did it change" parsed as `uncertain` (agent says it cannot know) | 0 | 26 | 12 |
| T4 message acknowledges having no memory of earlier sessions | 0 | 33 | 17 |
| tool calls touching paths outside the working directory | 1 | 22 (v1 left transcripts readable; one run read them) | 7 (scratch demos in /tmp, one look at an empty memory directory, one git reflog; nothing to read) |
| auto-memory files written | 0 | 4 (all at T4) | 1 (at T4) |
| explicit TodoWrite plans / commits / separate notes files | 0 | 0 | 0 |

Reading: in the continuous arm the agent cites its own earlier decision; in the fresh arm it reads
the repository, finds the decision embodied in the code and usually named in a docstring, and
continues it. In v2 the fresh arm had nothing to read but the repository; 17 of 20 say explicitly
that they cannot know whether the approach ever changed, and the 6 that speak of "choosing" are
describing the code they found. No harness-managed plan or memory artefact was used (the memory
notes were written at the last turn). These indicators say where the decision was recorded: in the
implementation, in docstrings and SPEC.md addenda the agent wrote, and, in the continuous arm, in
the transcript. They do not show that any of these *carried* the decision: no run removed a
candidate record (stripping the docstrings and SPEC addenda between fresh turns, or swapping in the
other approach's code) to see whether the choice survived, and a fresh instance re-deriving the same
preference from SPEC.md and the tests would produce the same table. That manipulation is the next
experiment, not a result of this one.

## 3. Experiment 2 changes the picture

See `docs/experiment2-hangman.md`. One fact governs all of it: in a continuous session the model's
own write tool call, containing the word, is in its context from turn 1, so no hangman arm tests a
record carrying a decision across a break in context. Within that limit: under a declared referee
rule the word given midway was the word given at the end in 96 of 96 games (one-sided 95% upper
bound on the switch rate about 3%), in bare chat and every tool condition; the model refused to play
the unannounced version at all (9 of 9 refusals), which is itself a finding about this model. The
residual failures are letter-level errors on a word that was fixed and, in the ceiling arm, re-read
before every reply; forced consultation made the model *worse* (10 of 24 inconsistent vs 2 of 24
bare, one-sided Fisher p ≈ 0.01), so the read-then-answer loop interferes with board rendering
rather than helping. Given a scratch directory the model writes the word down unasked in most games
and reads it back in almost none. The contrast with the coding experiment (record consumed on every
turn because the code is what gets extended and tested) is a plausible mechanism for when an
external record matters, but it is a proposal this study did not test, not a result.

## 4. Alternative explanations, and what the v2 arms say about them

- **Cost of change.** In the strong arm every run opened the drop-in and none adopted it (three
  borrowed pieces of it). With switching reduced to a copy, persistence held 10/10, so the cost of
  *rewriting* does not explain the temptation result. But the arm did not remove other costs, and
  the second review showed it supplied reasons: the prompt's parenthetical "(it may also contain
  extra features we don't need)" was cited as a reason by 9 of 10 runs; the drop-ins are the study's
  full reference solutions, so they really do carry later-turn features and docstrings naming their
  approach; and they were written to pass tests, so the agents found real defects in them
  (unquoted CSV cells, an `import_` that overwrites ids). A careful engineer declines a labelled,
  over-featured, less careful file regardless of commitment. The result stands as "did not switch
  when switching was free"; it does not isolate commitment from review and quality costs.
- **Instruction following / continuation prompt.** With the neutral prefix and no readable
  transcript, the fresh arm still kept its choice 10/10 and switched 10/10 after evidence. "Pick one"
  at T1 is the only instruction that could be doing work, and fresh sessions never saw it after T1.
  For `expr` specifically, the "irrelevant" nudge ("adding operators like `**` tends to be a one-line
  table entry") arrives on the turn whose feature is adding `**`, so it is task-relevant advice; that
  cell is weaker than the others.
- **Prior re-derivation.** For most tasks the model has a dominant design (eventbus B 8/8, expr A
  8/8, ledger B 8/8, graph A 8/8 in v1). A fresh instance re-deriving the same preference from
  SPEC.md would look identical to one maintaining a state. Nothing in either dataset separates
  these; the hangman result (the same prior over words, "picture" in roughly half the games)
  suggests priors do a lot of the work. The strong arm's reasons are about the *existing code*
  (compatibility, guarantees earlier work relies on), which is what maintenance rather than
  re-derivation would produce, but that is an interpretation of prose, not a measurement.
- **Instrument grain.** The `expr` reclassification shows how much a detector's notion of "the same
  approach" matters; the agents' self-reports were finer-grained than the first instrument.

## 5. Notable runs

**Strongest positive example.** `wire__ctx-strong__r1`: offered a working JSON-lines codec as a
drop-in, the agent read it, declined it because switching "would silently change the wire format
for anything already written" and drop its checksum, and extended its binary format instead. In
v1, `catalog` shows the pair: under temptation the agent kept sequential ids and explained why it
declined the UUID suggestion; under evidence it switched cleanly to UUIDs with the docstring
recording the switch and its reason.

**Strongest counterexample or failure.** There is no run in which the agent abandoned its
approach under temptation, so the counterexamples are about the instruments and the design rather
than the agent: the `expr` evidence runs, which moved to a table-driven hybrid while calling it
Approach A (the detector and the agent disagree about what counts as the same approach); the
ledger run that a first version of the mixed rule scored as a mixture and the second review showed
to be a cached event-sourced design; the strong arm's prompt handing the agent a reason to decline;
and Experiment 2 as a whole, where writing the word down changed nothing and forcing the model to
read it made it worse.

**Surprising behaviour.** Fresh-session agents were candid about not knowing their own history
(26 of 33 in v1, 17 of 20 in v2) and went looking for evidence in git, bytecode caches and, in v1,
Claude Code's own transcript directory. In hangman, the model wrote a secret file even when only
told a directory existed (18 of 24 games) and then ignored it, and refused a mid-game reveal until
it was declared a rule of the game.

## 6. Measurement failures, displayed rather than hidden

- The statement parser was revised twice against v1 messages; CONTROL under the original parser
  and the final one are both reported (`RESULTS-v1-original-scoring.md`, `RESULTS-v1.md`).
- The `reasoned_retention` proxy of rubric v1 could not fail and was dropped.
- Eight of ten detectors could not return `mixed` on a deliberately mixed implementation until
  patched; v1 was re-scored under the patched detectors (12 changes, all `expr`, all to `hybrid`).
- In v2, 12 of 20 fresh-arm T4 answers about "did it change" were classed `uncertain` (the agent
  said it could not know), which is correct behaviour for an agent with no memory and is reported
  as such rather than as a mismatch.
- Two detector rules added after the first review misfired (a one-entry alias map counted as a
  precedence table; a cached event-sourced ledger counted as a mixture) and were the only
  departures from ceiling in v2 before the second review corrected them. The ledger boundary is
  not mechanically decidable and is flagged rather than decided (`docs/review/mixed-validation.md`).
- Experiment 2's working-directory names contained the condition label (the same leak fixed for
  the coding experiment in v2); no game's text refers to it, but the "silent" arm's claim that only
  Claude Code's own cwd line hinted at a directory is weaker for that reason.
- Experiment 2's five middle arms were added iteratively and measure carefulness, not carrying; both
  the preregistered outcome and the post-hoc failure classes are shown.
