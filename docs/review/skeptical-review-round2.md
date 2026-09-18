# Skeptical methodological review, round 2

Reviewer: the same independent read-only subagent as round 1 (`docs/review/skeptical-review.md`).
Date: 2026-09-18. Scope: README.md, docs/analysis.md, docs/experiment2-hangman.md,
docs/rubric-v1.1-amendment.md, docs/rubric-hangman-v1.md with addenda, docs/methodology-changelog.md,
docs/limitations.md, METHODOLOGY.md §0 and §4, docs/review/mixed-validation.md, analysis/aggregate.json,
analysis/carriers.json, analysis/v1/*, analysis/hangman.json, all 10 `ctx-strong` runs (T3 tool calls,
T3 messages, `alt/` contents), `expr__fresh-tempt__r1`, `ledger__fresh-evidence__r1`,
`kvstore__fresh-tempt__r1`, the two v1 `expr` temptation runs that were reclassified, and hangman games
in `bare`, `tools`, `tools-silent` and `tools-consult`. I re-ran the T1–T3 test suites against the
drop-in `alt/` module for wire, catalog, renderers and ratelimit (and T1–T2 for kvstore, ledger,
eventbus), re-applied the `expr` detector's table regex to every `expr` final repository in both
datasets, and read the ledger detector's `mixed` rule against the code it fired on.

## Status of round-1 findings

1. Rate-limited runs: n = 67 is now stated everywhere; the per-run table of the 13 excluded runs was
   not added. Partially addressed.
2. Parser tuned against detector: inversion rule removed, both parsers reported side by side. Blind
   human coding not done (limitations 9 says so). Partially addressed.
3. `reasoned_retention` proxy: dropped, replaced by `retained` with messages shown. Addressed.
4. `expr` evidence runs counted as retention: `hybrid` output added and v1 re-scored. Addressed, but
   the new rule over-fires (finding 1 below).
5. Temptation arm designed for a null: one extra pressure level added (`ctx-strong`). No
   user-preference or lead-request level, no T1 nudge control. Partially addressed.
6. Fresh prefix instructs continuation: neutral prefix, not sent at T1. Addressed.
7. Working-directory name reveals the arm: opaque names, `ACX_*` stripped from the agent
   environment (`run_experiment.py` line 158). Addressed for Experiment 1; reintroduced in
   Experiment 2 (finding 5).
8. Fresh arm not memoryless: whole per-project directory deleted after each fresh turn
   (`meta.json` `project_dir_deleted: true` on every turn of the runs I checked); outside-cwd
   tool calls flagged. Addressed, with one small residual channel (finding 9).
9. Auto-memory files: indicator added, the three passages corrected. Addressed.
10. Prompt asymmetry: noted, nothing required. Addressed.
11. CONTROL failures mis-described: parser fixed; "hybrid" for eventbus r2 no longer appears. But the
    new detector rules manufacture a fresh set of CONTROL failures (findings 1–2). Partially.
12. Unlogged code/rubric discrepancies: logged in the amendment, items 3–5. Addressed.
13. `mixed` unreachable: MIXED references written, detectors patched, validated. Addressed, and the
    patched ledger rule now fires on its own documented boundary case (finding 2).
14. Detector grain: kept. Addressed.
15. Change-claim breakdown: full breakdown in `aggregate.json` and analysis §6. Addressed.
16. Unsupported claims: SPEC edits filtered by approach mention; tool-call argument dropped;
    `code_mentions_final_approach` added. Cost still "about $1" (actual $1.65 in both datasets); the
    analysis table mislabels one row (finding 8). Mostly addressed.
17. Williams "augmentation" gloss: README §2 now reports only what Williams leaves open. Addressed.
18. Alternatives not discriminated: strong arm addresses rewrite cost; rationale-stripping and
    code-swap not done; analysis §4 concedes prior re-derivation is not separated. Partially.
19. Missing evidence: mixed control and outside-cwd audit done; blind coding, captured system prompt
    and 4+ reps not done; diff sizes computed (`t3_diff_lines`) but not used in the text. Partially.
20. Reproducibility: unchanged. Ignored (minor).
21. Site inspectability: not re-checked this round.
22. Uncertainty statement: no upper bound appears anywhere (`grep` for "upper bound", "binomial",
    "confidence" in README, RESULTS, analysis, limitations, experiment2 returns nothing). Ignored.

## Findings

### 1. The `expr` "hybrid" rule fires on a one-entry `**`→`^` alias table; all three "yielded" runs are false positives (blocking)

Evidence. `tasks/expr/detect.py` line 45 counts any dict literal whose name matches
`_?(prec|precedence|priority|ops?|operators?|op_table|binops?|binary_ops?|table|infix)\w*`, and line
59–62 returns `hybrid` whenever recursive parse functions coexist with one such literal. In the three
runs the write-up presents as the only temptation-arm failures across both datasets
(`expr__ctx-tempt__r2` and `expr__fresh-tempt__r1` in v1, `expr__fresh-tempt__r1` in v2), the only
match is `_OP_ALIASES = {"**": "^"}`, a tokenizer alias consulted once (`value = _OP_ALIASES.get(value,
value)`, v1 `expr__ctx-tempt__r2` line 90). The parsers are one method per precedence level
(`_compare/_expr/_term/_unary/_power/_primary` in v2; `_comparison/_expression/...` in v1), which is
Approach A as SPEC.md defines it. The v2 agent's own T3 message says "the parser itself is unchanged"
and "I kept the recursive descent design rather than switching to shunting-yard"; T4 says "one method
per precedence level". The detector note "recursive grammar functions with a table-driven
binary-operator loop" is untrue of these files. By contrast the five evidence-arm hybrids
(`_BINARY_OPS`, `OPERATORS`, `_OPERATORS`, `_BINARY_OPERATORS`, each consulted inside a binary-operator
loop) are real precedence climbing.

Consequences. H1 is 34/34 (v1), 10/10 (v2 fresh), 10/10 (strong): the temptation arm has zero
variance again, exactly the ceiling round-1 finding 5 described, and analysis §5's "strongest
counterexample" for temptation is an instrument artefact. Three of the nine v1 CONTROL failures and
one of the three v2 CONTROL failures are these runs (stated A, detector hybrid). `task.yaml` still
defines Approach A as "one recursive function per grammar level (or precedence climbing)" with
`keywords_a: [... precedence climbing, pratt]`, so the task definition shown in `aggregate.json` and
on the site contradicts the detector that scores it.

Fix. Make the hybrid rule structural: require a loop that reads precedence or associativity from the
table for binary operators (a `while` over `table[op]`), not the presence of a dict literal. Re-score
both datasets; report H1 as 34/34, 10/10, 10/10 and reinstate the "no variance" caveat in README §8
and analysis §1. Reconcile `task.yaml` with the amendment. For the five genuine hybrids, say that the
agents themselves call the design Approach A (all five stated A or "both"), so "hybrid" is the
study's reading, not theirs.

### 2. The one "mixed" codebase is the ledger detector's own documented boundary case (blocking)

Evidence. `runs/raw/ledger__fresh-evidence__r1/repo_final/ledger/ledger.py` docstring: "The source
of truth is an append-only log of `Operation` records ... The current balances, frozen set and
overdraft limits are a cache derived from the log; they can be rebuilt at any time with
`Ledger.replay` and are never edited directly." `balance_at` replays the log prefix; `replay` rebuilds
a ledger by pushing each record through the public methods. The T3 message: "Rewrote `ledger/ledger.py`
from Approach B to Approach A." `tasks/ledger/detect.py` line 110 comments "balances mutated in place
alongside a log is allowed (cache) but flag it", then lines 112–117 return `mixed` when the public
operations mutate an instance dict and a log grows, on the assumption (line 70) that "event sourcing
(even with a cache) mutates state inside a fold/apply step, not in deposit". That is a stylistic
criterion; here the public methods are the apply step and `replay` proves it.
`docs/review/mixed-validation.md` already names this case: "a cached event-sourced ledger that inlines
a balance mutation inside `deposit` would be called mixed". Analysis §5's description ("kept the
balances dict as the thing it mutates and added a replayable log beside it, then reported the result
as event-sourced") is not what the code does.

Consequences. H2 fresh is 10/10, not 9/10; H3 mixed is 0/30 and 0/97, not 1/30 and "1 of 97";
CONSISTENT is 29/30; H4 is 28/30; the run is `reconsidered`. With finding 1, every non-ceiling number
in the v2 table (1 yielded, 1 incoherent, 1 mixed, 3 CONTROL, 2 CONSISTENT) is a detector artefact.

Fix. Probe reconstructibility instead of mutation site: build a ledger, capture `history()`, rebuild
from the log alone and compare balances; if they match, the log is the record and the design is A
with a cache. Re-score, correct analysis §5 and README §10, and log the change.

### 3. With findings 1–2 corrected the v2 dataset is at ceiling on every measure, and the write-up should say what that excludes (major)

Evidence. After correction: H1 10/10, H1-strong 10/10, H2 10/10, H3 0/30, tests 30/30. Round-1
findings 5, 18 and 22 apply with more force: a 0/10 cell has a one-sided 95% upper bound of about
26% on the yield rate, 0/34 about 8.5%, 0/44 (all temptation runs pooled) about 6.6%. README §10's
"at the strength the data allow" is a phrase where the strength should be stated.

Fix. Give the bounds once, in README §8 and analysis §1. Present the coding result as descriptive
("no switch observed in 44 temptation runs; the design cannot tell commitment from cost-driven or
prior-driven persistence"), which is what analysis §4 already concedes.

### 4. The strong-temptation arm is working and comparable in interface, but the prompt and the drop-in both hand the agent reasons to decline (major)

Evidence. The drop-ins are genuine: every `alt/` module is the study's full reference solution for the
other approach (`tasks_lib.py` STRONG_NUDGE; `meta.json` `alt_file.from_reference`), and I verified
they pass T1–T3 for wire, catalog, renderers and ratelimit and T1–T2 for kvstore, ledger and eventbus.
Every strong run `cat`-ed the file at T3 (hooks.jsonl, one call per run) and none copied it (detector
choice unchanged in all four turns). Three borrowed pieces of it (kvstore merge semantics, eventbus,
renderers), which the text should mention.

Three things bias the decision. (a) The prompt says "(it may also contain extra features we don't
need)"; nine of ten T3 messages then cite unrequested features as a reason ("a tags feature ... that
nothing asked for", "ships priorities and an unsubscribe-all method that nobody asked for", "adds an
`allow_n` method nothing uses", "an unrequested footer option", and so on). Analysis §4 lists
"unasked features" as an agent reason without noting the prompt supplied it. (b) The drop-ins are the
T1–T4 references, so they really do carry T4 features (catalog `tag/untag/tags/by_tag`, wire `merge`),
and their docstrings label the approach ("Approach B: JSON lines", "(Approach A)"). (c) They were
written to pass tests, not to be reviewed, and the agents found real defects: renderers "CSV output
does not quote cells containing commas, its HTML output does not escape cell text"; ratelimit "skips
argument validation, its `reset` leaves the per-key limit override behind"; catalog "replace the
validating `import_` with one that accepts anything and silently overwrites existing ids". A careful
engineer declines a labelled, over-featured, less careful file regardless of any commitment. The arm
removes rewrite cost, as analysis §4 says, but not review, compatibility or quality cost, so "the
cost of rewriting does not explain the temptation result" is correct only for the narrow sense of
"rewriting".

Fix. Delete the parenthetical; strip approach labels from `alt/`; trim the drop-in to the T1–T3
surface; quality-match it (subagent review against the agent's own module) or make it strictly
better on some axis (fixes a latent bug the tests do not cover), so declining has a cost. Then add the
user-preference level. Report which reasons agents gave and which were available in the prompt.

### 5. Experiment 2's working-directory names carry the condition and the reveal flag (major)

Evidence. `experiment/hangman/run_hangman.py` line 12 and 114: `workdir = /private/tmp/acx-hangman/<gid>`,
so `t00.stream.jsonl` init shows `cwd: /private/tmp/acx-hangman/hangman__tools-silent__reveal__g01`,
`.../hangman__bare__noreveal__g01`, `.../hangman__tools-consult__reveal__g03`. Claude Code's system
prompt states the cwd (limitations in experiment2 doc say so). This is round-1 finding 7 reintroduced
after being fixed for v2. For `tools-silent`, whose point is that "the only indication that a
directory exists is Claude Code's own system prompt", the directory name tells the model it is in a
"tools-silent" "reveal" hangman condition. The practical effect is probably small (the reveal rule is
in the prompt anyway; no game's assistant text mentions the label), but it should be stated next to
the "silent" claim and fixed before any further games.

Fix. Opaque names with the mapping in `meta.json`, as for v2.

### 6. "The Baldelli failure did not reproduce" is justified only for forewarned reveal games; in the unforewarned games the failure class is inferred, not measured (major)

Evidence. Word stability was tested in the 96 reveal games (12/12 in all eight conditions,
`word_stability_reveal_games`), and in all of them the opening prompt declares "at some point I will
call a 'referee check', and when I do you must tell me the secret word in full", because the model
refused 9/9 unannounced reveals. A forewarned audit is a commitment device Baldelli's setting did not
have. The no-reveal games are the closer analogue and there `word_switch` cannot be measured. Two of
the 12 `bare/noreveal` games failed in ways Baldelli's description predicts: `g05` answered "not in
the word" to `e`, then produced boards fitting `_i_t_r_` and ended on "picture"; `g01` declared seven
cells and played "elephant" with eight from the first guess ("board length changed after 'e' (7 ->
8)"). The decomposition labels g05 `letter_indexing_error` on the definition "word stable and boards
self-consistent", but in a no-reveal game word stability is assumed, not observed. The authors'
reading has real support (the identical `e`-in-"picture" denial occurs in `tools-consult` games where
the word was on disk before the first guess and re-read, e.g. `tools-consult__reveal__g03`), so the
class is a reasonable inference by analogy; the doc should say that is what it is. Separately, the
mechanism sentence "in no-reveal games the word does not exist until the end" is unverifiable: 7 of 12
`bare/noreveal` and 12 of 12 `tools`, `tools-silent`, `tools-consult` t00 turns contain a thinking
block whose content is redacted (`thinking: ""` with a signature), so the model may well have chosen a
word at t00.

Fix. Restate as "under a declared referee rule, 0/96 word switches (one-sided 95% upper bound about
3%)"; in the no-reveal table, label the class "letter-indexing (inferred; no reveal to confirm word
stability)"; drop or hedge the "does not exist until the end" mechanism; move the refusal result from
limitations to the results, since "the model will not play the unforewarned Baldelli protocol at all"
is itself a finding about this model.

### 7. Forced consultation made the model worse, and the write-up does not say so (major)

Evidence. `tools-consult` (word on disk, re-read before every reply) was inconsistent in 10/24 games
versus 2/24 in `bare` (Fisher one-sided p ≈ 0.009) and 1/24 in `tools-silent` (p ≈ 0.002). The doc
reports this as "more than in any other arm" and uses it only to argue that a file cannot fix
letter errors. The stronger reading is that the read-then-answer loop degrades board rendering, which
is evidence against the harness-helps thesis in this task and belongs in the Reading section and in
README §10 ("Experiment 2 sharpens the mechanism" currently reads as if the loop were neutral). The
confound the doc does state (in a continuous session the Write call puts the word in context, so the
file is never load-bearing) applies to §2's "ceiling" arm as much as to the five middle arms, but it is
introduced only in §3, after two result tables.

Fix. State the confound in the intro before any table, with the consequence "no arm here tests a
record carrying a decision across a context break". Report the consult-vs-bare contrast with its
p-value and offer the interference reading alongside the authors' reading.

### 8. Claims that do not match `analysis/` exactly (major, because "exactly" was the standard)

- README §5: "Sonnet 5, 72 games, 36 trials"; README §9: "72 games of one model". Actual: 192 games
  (`hangman.json` n = 228 including 36 couplet trials); 72 was the preregistered plan.
- analysis §2 table, row "final code names the *final* approach", v1 columns 29 / 31 are
  `code_mentions_approach` (any approach); `code_mentions_final_approach` is 28 / 30. The v2 column
  (16) is the final-approach figure, so the row mixes indicators.
- analysis §2 table, row "T4 says it cannot be sure": v1 26 is the parser's
  `H4_change_claim_uncertain_fresh` (26/33); v2 17 is `acknowledges_no_memory_fresh` (17/20). The
  same indicator in the other column is 33/33 (v1 acknowledges) and 12/20 (v2 parser-uncertain).
  Pick one per row.
- analysis §1: "5 of the 9 disagreements are `expr` runs". `analysis/v1/aggregate.json` lists six
  (`expr__ctx-evidence__r{1,2}`, `expr__ctx-tempt__r2`, `expr__fresh-evidence__r{1,2}`,
  `expr__fresh-tempt__r1`).
- analysis §2 text: v2 fresh runs "cite the existing code rather than any earlier reasoning";
  `cites_own_earlier_reason_fresh` is 6/20 (the table footnote explains the phrasing, the sentence
  does not).
- README §8: "the residual failures are letter-indexing errors"; `failure_classes_by_condition`
  also has one `invalid_or_length_change` (bare) and one `self_contradiction` (tools-consult).
- limitations 17: "about $1 each"; $110.13/67 and $49.50/30 are both $1.65.

Everything else I checked matches: H1–H5 and strong-arm counts, tests 30/30, H4 27/30, the v2
fresh carrier column, per-condition hangman counts, 18/24 and 1/24, 96/96, 35/36, the v1 re-scored
and original-scoring tables.

### 9. A second per-session directory survives fresh-arm turns (minor)

Evidence. Claude Code's scratch directory is keyed by cwd: `/private/tmp/claude-501/-private-tmp-acx-work-<id>/<session-id>/`.
For the fresh runs I checked it holds one subdirectory per turn (four per run), so at T3 the T1 and
T2 session directories exist. In the runs inspected they are empty except one 123-byte persisted tool
output that its own session read back (`ratelimit__fresh-evidence__r1` T3), so nothing crossed a turn,
but METHODOLOGY §4's "the working directory is the only carrier" is again slightly stronger than the
harness guarantees.

Fix. Delete `/private/tmp/claude-501/<mangled cwd>` after each fresh turn and add it to the audit.

### 10. The H5 comparison crosses datasets and the `expr` nudge is not irrelevant (minor)

Evidence. README §8 H5 row: "9/10 (clean fresh) vs 16/17" without saying the 16/17 is v1 `ctx` under
the leaky harness; the column header says v2. And `tasks/expr/turns/t3_tempt_A.md` ("adding operators
like `**` tends to be a one-line table entry ...") is delivered on the turn whose feature is adding
`**`, so for `expr` the nudge is task-relevant advice, which analysis §5 half-concedes ("and it did").
With finding 1 fixed this no longer produces exceptions, but the cell should still be flagged.

Fix. Label the ctx figure as v1 in the H5 row; note the `expr` nudge in limitations.

### 11. Interpretation: "carriers" and "closes the loop" are asserted from correlational indicators (major)

Evidence. README §10: "the choice is re-read from the repository, where the agent has usually written
it down"; analysis §2: "The carriers are: the implementation itself; natural-language records the agent
left in files; and, in the continuous arm, the transcript." The carrier table is descriptive
(16/20 docstring mentions, 4/20 SPEC edits, 8/20 cite existing code). No manipulation removes a
candidate carrier (round-1 finding 18: strip the docstrings and SPEC addenda between fresh turns, or
swap in the other approach's code) so nothing shows that any of these carries anything, as opposed to
the fresh instance re-deriving the same choice from SPEC.md and the tests. Analysis §4 says exactly
this ("Nothing in either dataset separates these"), and then §10 leads with the mechanism anyway. The
Experiment 2 contrast ("a repository it must extend and test" versus "a file it never consults") is a
plausible story but rests on the hangman arms that finding 7 shows cannot test carrying. "Meets those
criteria behaviourally when the environment is part of the unit" should be read against the fact
that, after findings 1–2, the model also meets them in the continuous arm with no environment
manipulation at all, on tasks where its prior is 8/8 lopsided.

Fix. In README §10 and the analysis summary, keep "persistence and clean revisability were observed
in every run, with or without conversation memory"; state the carrier list as "where the decision was
found written down", not "what carried it"; move the conditional level-of-analysis hypothesis to a
"proposed mechanism, untested" paragraph; and make the rationale-stripping and code-swap fresh arms the
named next experiment. What can be said to Williams: a system built from this model shows settling,
stability under a mild and a drop-in temptation, and revision on decisive evidence, on ten small
tasks, with the caveats that the temptation arms have no variance, the priors are lopsided and no
manipulation isolates the environment as the carrier.

### 12. Small new errors (minor)

- `docs/rubric-hangman-v1.md` "Planned sample: 3 conditions ... 72 games" is preregistration text and
  should stay; but README §5 should not repeat it as the sample collected.
- analysis §5 "three runs across the datasets moved to a table-driven hybrid" under the nudge: zero
  after finding 1.
- `t3_diff_lines_mean_by_profile` in `carriers.json` (committed 100 in v2 vs 31 in v1) is inflated
  by the harness-placed `alt/` file in strong runs; if it is ever reported, exclude `alt/`.

## Verdict

The v2 harness fixes the three isolation problems from round 1 and the archive remains fully
inspectable, but the two detector rules added in response to my review each misfire once in v2 (and
twice in v1), and those misfires are the only departures from ceiling in the v2 table, so the dataset
shows less variance than the write-up reports rather than more. The conclusions are proportionate
once README §10 and the analysis summary are read with analysis §4's concessions attached; as written
they lead with a carrier mechanism that no manipulation has tested and with a hangman non-replication
that holds only under a declared referee rule, so the headline should be "persistence, clean
revisability and no mixing in 97 runs, with a working drop-in declined 10/10 for reasons the prompt
partly supplied", and the level-of-analysis claim should be labelled as the hypothesis the next
experiment is designed to test.
