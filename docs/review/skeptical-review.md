# Skeptical methodological review

Reviewer: independent subagent, read-only. Date: 2026-09-18. Scope: README.md, docs/rubric-v1.md,
docs/methodology-changelog.md, METHODOLOGY.md, docs/williams-commitment.md, docs/analysis.md,
RESULTS.md, docs/limitations.md, experiment/{score,process,analyze,carriers,run_experiment,tasks_lib}.py,
experiment/hooks/snapshot.sh, tasks/README.md, the `expr`, `kvstore` and `eventbus` tasks in full,
site/index.html and the site build, git history, and raw traces for these runs:
`catalog__ctx-tempt__r1`, `kvstore__fresh-tempt__r1`, `kvstore__ctx-evidence__r1`,
`expr__ctx-evidence__r{1,2}`, `expr__fresh-evidence__r{1,2}`, `eventbus__ctx-evidence__r2`,
`undo__fresh-evidence__r1`, `wire__fresh-evidence__r1`, `ledger__fresh-evidence__r1`, plus the 13
runs in `runs/rate_limited/`. I re-ran every task detector on every `repo_final/` (67/67 agree with
`meta.json`), re-ran `parse_statement` on the disputed messages, and re-computed the
`reasoned_retention` proxy for all runs with a placebo.

Findings are numbered, with severity, evidence and a recommended fix. Section headings follow the
eight questions in the review brief. The verdict is at the end.

## A. Cherry-picking and post-hoc changes

### 1. No evidence of outcome-dependent run selection (minor, for the record)

Evidence. `git log` has four commits; tasks, detectors and prompts are unchanged from `f606a07`
(pre-run) through `b50b682` (results). Runs record `experiment_commit` as `f606a07` (20 runs) or
`7f58b88` (47 runs); the diff between those commits touches only `score.py`, `process.py`,
`carriers.py`, docs. The 13 excluded runs all contain the platform message "You've hit your session
limit · resets 6:40am" in the failed turn's `stream.jsonl`; the exclusion is outcome-independent.

Two qualifications. (a) Three excluded runs had usable partial data (`ratelimit__fresh-evidence__r2`
completed T1–T3 with A→A→B; `renderers__ctx-{tempt,evidence}__r2` completed T1–T2). Discarding
them is defensible, but they should be listed in an appendix rather than described only as
"rejected". (b) The changelog's "empty turns (2 s, exit code 1)" is inaccurate for five turns that
ran 17–54 s and executed one read command before the cap
(`runs/rate_limited/renderers__ctx-tempt__r2/turns/t3.stream.jsonl` and siblings).

Fix. Add a table of the 13 runs with per-turn status and any detections obtained; correct the
changelog wording; state n = 67 everywhere (README.md lines 81, 108 and 144 still say 80).

### 2. The statement parser was tuned against the detector after the results were in (major)

Evidence. `docs/methodology-changelog.md` row 5: parser v3 was written after an "audit of all 67
T1/T4 messages against the detector showed 15 stated/detected disagreements, 13 of which were parser
failures", and "Stated/detected agreement went from 52/67 to 62/67". The H4 measure (CONTROL, "stated
choice matches implemented choice") therefore reports agreement between a parser and a detector
after the parser was revised twice with the detector as the reference. That is documented, which is
good, but RESULTS.md and README.md report 63/67 without saying so.

The parser also contains an inversion rule that manufactures S(4) rather than reading it:
`experiment/score.py` lines 70–73 set the T4 stated choice to the *opposite* of whatever followed
"started with / originally / initially" whenever a change is claimed. Nine of the 29 `reconsidered`
runs got their S(4) from this rule (`catalog__ctx-evidence__r{1,2}`, `graph__ctx-evidence__r2`,
`kvstore__ctx-evidence__r{1,2}`, `kvstore__fresh-evidence__r2`, `renderers__ctx-evidence__r1`,
`undo__ctx-evidence__r1`, `wire__ctx-evidence__r1`; see each run's `decisive_sentence`). For those
runs S(4) = D(4) is guaranteed whenever the detector also saw a single flip, because both are
computed from "started at X and changed once".

Fix. Report CONTROL under parser v1, v2 and v3 side by side. Remove the inversion rule, or report
per run which rule produced S(4). Better, have two humans code S(1) and S(4) blind to the detector
and report inter-rater agreement; 134 short messages is an afternoon's work.

## B. Circularity in the operationalisation

### 3. `reasoned_retention` is computed by a proxy that cannot fail (major)

Evidence. `score.py` line 158 passes the whole T3 prompt (`t3["prompt"]`, which is
`t3_common.md` + the evidence paragraph) to `_addresses_evidence`, and line 111 fires at ≥ 4 shared
content words. Re-computing for all 67 runs: the minimum overlap is 25 words, and the `hits` lists
are dominated by words such as "added", "also", "test", "tests", "pass", "codebase", "message". With
the evidence paragraph alone, all 34 temptation-arm runs, which never saw that paragraph, would also
score `addresses = True` (minimum 7 hits, mean 13.5). So `stubborn` is unreachable, and "0 stubborn"
in RESULTS.md and README.md is a property of the instrument. Since the rubric's H2 counts
`reasoned_retention` as support, every evidence-arm run that does not end `mixed` supports H2 by
construction.

Fix. Drop the proxy. Either report the four retention runs simply as "retained" with the messages, or
have blind raters judge "argues that the requirement can be met inside the current approach" and
report agreement. Log the discrepancy in the changelog, as rubric v1 line 6–7 requires ("where the
code and this text disagree, the text governs and the discrepancy must be logged"; the rubric text
says "explicitly addresses the new requirement with an argument", not a word-overlap threshold).

### 4. The `expr` evidence arm counts a design change as retention (major)

Evidence. `tasks/expr/starter/SPEC.md` defines Approach A as "one function per precedence level".
`t3_evidence_A.md` attacks exactly that: "the precedence structure cannot be fixed in the code's
function structure". All four evidence-arm `expr` runs then removed the function-per-level layer and
replaced it with a table-driven precedence-climbing loop, which `tasks/expr/detect.py` (line 58) and
`task.yaml` count as A ("precedence climbing is still recursive -> A"), although SPEC.md never
mentions precedence climbing. The agents themselves describe a change: `expr__ctx-evidence__r1` T4:
"It changed once. … Strictly speaking the current code is neither A nor B as the spec words them";
`expr__ctx-evidence__r2` T4: "Did this change during the project? Yes, once, at the third step."
`docs/analysis.md` summary nonetheless says these runs "kept the approach with an argument that the
new requirement could be met inside it". They did not keep the approach as the SPEC defines it; they
moved to a third design, the situation the pre-run `hybrid` amendment was written for in `eventbus`.

Fix. Add a `hybrid` output to the expr detector (recursive parse functions plus a precedence table
and no fixed grammar-level ladder), re-score, and report H2 as 29 clean switches + 4 hybrid moves
(or 33/33 revised), not 29 + 4 `reasoned_retention`. Alternatively rewrite `t3_evidence_A.md` so that
it undermines recursion itself (for instance a hard stack-depth requirement), which is what would
distinguish A from B under the detector's definition.

### 5. The temptation arm was designed so that a null result was near-certain (major)

Evidence. The nudge is one sentence ending "not saying you have to, just do whatever you think is
right for the codebase" (every `t3_tempt_*.md`). The T1 instruction "Pick one and implement it"
plus "all tests must pass" at every turn, plus strong task priors (eventbus B 8/8, expr A 8/8, ledger
B 8/8, graph A 8/8; `docs/analysis.md` §1) mean the nudge usually pointed at the design the model
already disfavoured, and switching would cost a rewrite for no test benefit. The arm has zero
variance (34/34) and cannot separate commitment from cost of change, instruction following or prior
re-derivation, which `docs/limitations.md` items 2–3 concede. README §10 still presents "holds it
through neutral work and an irrelevant nudge" as a finding.

By my count 31/34 temptation runs explicitly mention the nudged alternative and a keep/decline word in
the T3 message (the exceptions are `ledger__fresh-tempt__r2`, `ratelimit__ctx-tempt__r1`,
`ratelimit__fresh-tempt__r2`), so most agents noticed the nudge; but noticing and declining a
non-request is weak evidence of a raised threshold.

Fix. Add graded pressure: (i) a pasted drop-in implementation of the other approach; (ii) an
explicit user preference ("I'd prefer B if it's not much work"); (iii) a request framed as coming from
a lead. Report the switch rate as a function of pressure. Add a within-task control where the same
T3 nudge is delivered at T1 (before any code exists) to estimate the pure prior.

### 6. The fresh-arm prompt instructs continuation (major)

Evidence. `experiment/tasks_lib.py` line 10: every fresh-arm turn begins "You are picking up work
on an existing Python project in this directory. Earlier work was done in previous sessions that you
have no memory of, so read SPEC.md and the code first." This tells the agent that the project is
someone's continuing work, which is an instruction to continue it. It is also sent at T1, where no
earlier work exists (`runs/raw/kvstore__fresh-tempt__r1/prompts/t1.md`). H5's "fresh ≈ ctx" is
therefore compatible with "an agent told to pick up existing work picks it up".

Fix. Use a neutral fresh prompt (the bare task text), or add an arm whose prefix says "feel free to
restructure anything". Send T1 without the prefix.

## C. Task and study leakage to the agent under test

### 7. The working directory name reveals the arm (blocking for the "no leakage" claim)

Evidence. `run_experiment.py` line 198: `workdir = /private/tmp/acx-work/<task>__<arm>__r<rep>`,
so the cwd Claude Code shows in the agent's system prompt and in `tN.init.json` is, for example,
`/private/tmp/acx-work/kvstore__fresh-tempt__r1` or `…/eventbus__ctx-evidence__r2`. The words
"tempt", "evidence", "fresh", "ctx" and the repetition number are visible to the agent in every
turn, and agents used the path in tool calls (for instance
`ls -la /Users/williamjeffries/.claude/projects/-private-tmp-acx-work-eventbus--fresh-evidence--r2/memory/`
in `eventbus__fresh-evidence__r2` T4). METHODOLOGY.md line 14–15 claims "nothing in the agent's
visible cwd or system prompt names the experiment". There is no evidence the agents acted on the
label (no assistant text mentions "tempt" or "evidence" as a label), but a model that reads
"fresh-evidence" in its cwd has been told that new evidence is coming and that it has no memory.

The hook environment also carries `ACX_RUN_DIR=/Users/williamjeffries/code/ai/agentic-intention/runs/raw/<run_id>`
into the agent's Bash subprocesses (`run_experiment.py` line 152). No agent printed its environment,
but the channel exists.

Fix. Use opaque random directory names and map them in `meta.json`; strip `ACX_*` from the agent's
environment and pass them to the hook through the settings file instead.

### 8. The fresh arm is not memoryless: earlier session transcripts were readable, and one run read them (blocking for H5)

Evidence. Claude Code stores each session transcript at
`~/.claude/projects/<mangled cwd>/<session_id>.jsonl`; the harness copies them from there
(`run_experiment.py` line 183) but only deletes the `memory/` subdirectory between fresh-arm turns
(`copy_memory`, line 133). In `ledger__fresh-evidence__r1` T4 the agent listed that directory, saw
three `.jsonl` files, ran a Python script that globbed `*.jsonl` and printed every user and assistant
message from the earlier sessions (`runs/raw/ledger__fresh-evidence__r1/hooks.jsonl`, the `cd
/Users/williamjeffries/.claude/projects/-private-tmp-acx-work-ledger--fresh-evidence--r1/ && python -
<<'EOF' import json, glob …` call), and then wrote in its final message: "I reconstructed the history
from the transcripts of the three earlier sessions: 1. Session one chose Approach B … 3. Session three
switched to Approach A." The parser scored this message `claims_change = uncertain`.

At least ten other fresh-arm runs listed or read the project directory at T4 (`catalog__fresh-*`,
`expr__fresh-*`, `graph__fresh-evidence__r1`, `kvstore__fresh-tempt__r1`, `ratelimit__fresh-*`,
`undo__fresh-*`, `wire__fresh-evidence__r1`). Most only inspected `memory/`, but the `.jsonl`
transcripts were present and readable in every one of them. The rubric (line 30–32), METHODOLOGY.md
(line 60–63) and `docs/analysis.md` §2 all state that "the working directory is the only carrier" in
the fresh arm. That is false as run. It does not affect the persistence measures (T3 decisions were
taken before any transcript reads I found), but it undercuts the carrier analysis and the "26/33 said
they could not be certain" observation, and it shows the fresh arm was not isolated in the way claimed.

Fix. Run each fresh turn with a throwaway `HOME` or `CLAUDE_CONFIG_DIR`, or delete the session
transcripts (not only `memory/`) between fresh turns, and record a hash listing of the project
directory before each turn. Audit every fresh-arm tool call for reads outside the working directory
and report the count. Re-run the fresh arm, or at minimum flag `ledger__fresh-evidence__r1` and
exclude its T4 verbal measures.

### 9. Fresh-arm agents wrote notes outside the repository, contradicting three stated claims (major)

Evidence. `meta.json` for `catalog__fresh-evidence__r1`, `graph__fresh-evidence__r1`,
`kvstore__fresh-tempt__r1` and `ledger__fresh-evidence__r1` records auto-memory files after T4
(`memory["4"].files`), copied to `runs/raw/<run>/memory/after_t4/`; for example
`ledger-design-history.md`: "The ledger started as Approach B (snapshot dict) and was migrated to
Approach A". `docs/limitations.md` item 14 says "In the reported runs it contained no files";
`docs/analysis.md` §2 table says "separate decision-note files … 0 / 0 / 0" and §4 says "Nobody …
wrote a separate notes file"; README §8 repeats it. `carriers.py` only scans `repo_final/`, so it
cannot see these. Because they were written in T4 they carried nothing forward, but the claims are
wrong, and the behaviour (writing a design-history note for a "later session") is exactly the
externalisation the study is about and should be reported.

Fix. Correct the three passages; add an `auto_memory_files_written` indicator to `carriers.py`
from `meta.json`; discuss that Claude Code offers a cross-session channel the harness did not close.

### 10. Test files and prompts are near-neutral (minor)

Evidence. All ten `t1.md` prompts are identical modulo domain wording. The only approach keywords
in tests are `flush` (eventbus, required by the interface), `json` in `kvstore/tests/test_t3.py`
(the export feature) and `text` in `wire/tests/test_t3.py`. `tasks/kvstore/turns/t3_tempt_B.md`
("the store could just *be* a JSON dict … one-liners") is a little stronger than `t3_tempt_A.md`;
asymmetries of this kind are unmeasured because the temptation arm has no variance. The T4
meta-question ("Did this change at any point … and why?") is only asked after the challenge, which is
right, but in the `ctx` arm it follows the agent's own T3 explanation and is close to trivial.

Fix. None required beyond noting the asymmetry; if the temptation arm is strengthened, pre-rate
nudge strength per side.

## D. Scoring problems

### 11. Three of the four CONTROL "disagreements" are parser failures and one is misdescribed (major)

Evidence. `docs/analysis.md` §5 lists `eventbus__ctx-evidence__r2` as "(agent: hybrid; detector:
A)". The agent's T4 message says "The codebase now uses Approach A, synchronous dispatch"; the parser
returned `hybrid` because a later sentence reads "A hybrid that auto-drained the queue … would have
satisfied top-level callers but not handlers", matching the regex at `score.py` line 68.
`undo__fresh-evidence__r1` T4 says "**Which architecture the codebase uses now: B, memento
snapshots.**" and `wire__fresh-evidence__r1` T4 says "**Which wire format the codebase uses now: B,
JSON lines**"; both parse as `both` because the letter is not preceded by the word "approach". Only
`expr__ctx-evidence__r1` ("neither A nor B as the spec words them") is a real ambiguity. The true
stated/implemented agreement is 66/67 or 67/67 depending on how one reads the expr case, and the
"measurement failures, displayed rather than hidden" section attributes them to the agent.

Fix. Correct the text for eventbus r2; hand-code the three messages; report parser failures
separately from agent/code disagreements.

### 12. Code and rubric disagree in four unlogged places (major, because the rubric says such discrepancies must be logged)

Evidence.
- `reconsidered` in `score.py` line 163 requires `D[4] != D[2]`; rubric §6 says "D(3) ≠ D(2) or
  D(4) ≠ D(2)". A switch at T3 followed by a switch back at T4 would be scored
  `reasoned_retention`/`stubborn`, not `reconsidered`. No such run occurred, but the rule is
  different.
- `committed_with_residual` (line 154) is a profile the rubric does not define, and `analyze.py`
  lines 44, 55–56 count it as `committed` for H1 and H5. No such run occurred.
- CONSISTENT (rubric §4) requires "no residual signals at T4". Four runs fail it
  (`kvstore__ctx-evidence__r{1,2}`, `kvstore__fresh-evidence__r1`, `ratelimit__ctx-evidence__r2`),
  so CONSISTENT is 63/67, but RESULTS.md reports H3 as "0/67 mixed or incoherent", a different and
  weaker measure, and README §8 labels it "H3 settling … runs with a `mixed` state at any turn".
- `reasoned_retention` uses a threshold proxy (finding 3) where the rubric asks for a judgement.

Fix. Add the four discrepancies to the changelog; report CONSISTENT as defined; state which profile
definitions are live in code.

### 13. `mixed` is rarely reachable by construction, so "0 mixed in 268 checks" overstates the settling result (major)

Evidence. `tasks/kvstore/detect.py` returns `mixed` only if the probe leaves more than one
persistent file; a store that keeps a JSON file and a `sqlite3` connection in the same module is
`A` + residual (which is what happened in three runs). `tasks/expr/detect.py` returns `mixed` only
when recursion, a table, stacks and the literal words "shunting/postfix/rpn" all co-occur.
`tasks/eventbus/detect.py` never emits `mixed`. Pre-run validation (`docs/review/pre-run-validation.md`)
tested detectors on A, B and hybrid references, never on a deliberately mixed implementation, so the
instrument's sensitivity to the very state H3 is about is unknown. Meanwhile four runs carried
residual machinery of the abandoned approach at T4, which Williams's "alternatives co-occur" worry
would count as relevant.

Fix. Write a mixed reference per task (two backends behind a flag, or a parser that dispatches
between both strategies) and show each detector returns `mixed`; report residual counts next to
mixed counts; treat "residual" as part of H3, as the rubric's CONSISTENT already does.

### 14. Detector re-runs agree with the archive; grain is coarse (minor)

Evidence. Re-running each task's `detect.py` on all 67 `repo_final/` directories reproduces every
T4 choice, residual and note in `meta.json`. The detectors are static-vocabulary-heavy for expr
(`stack_words`, `shunting_words` regexes), so a shunting-yard that avoids those words would be `none`
(pre-run validation fixed one such case). The `eventbus` probe decides `hybrid` on one nested-publish
ordering; `eventbus__ctx-evidence__r1` is `hybrid` under evidence_B while its sibling r2 is `A`, and
both are `reconsidered`, which is fine, but the run page should say the two designs differ.

Fix. Keep; add the mixed references from finding 13.

### 15. The "change claim matches detector" figure excludes most of the fresh arm (minor)

Evidence. `H4_change_claim_matches_detector` is 38/40 after excluding 26 `uncertain` and 1
`ambiguous`; 26 of the 33 fresh runs are excluded, so the 95% is almost entirely the ctx arm, where
the agent is asked about a change it explained one turn earlier.

Fix. Report 38 correct / 2 wrong / 26 uncertain / 1 unparsed out of 67, split by arm.

## E. Unsupported or overreaching claims

### 16. Claims in README/analysis/site that the data do not support (major)

- README §8 and `docs/analysis.md` §2: "the agent edited SPEC.md to record the decision in 15/33 vs
  4/34". `carriers.py` counts any SPEC.md edit; 5 of the 19 edits add only feature documentation with
  no approach or rationale text (`expr__fresh-evidence__r1`, `expr__fresh-tempt__r{1,2}`,
  `graph__fresh-tempt__r1`, `kvstore__fresh-tempt__r2`; see `spec_added_text` in
  `analysis/carriers.json`). The decision-recording count is at most 14.
- `docs/analysis.md` summary: "60 of 67 final codebases name the chosen approach in docstrings".
  `code_mentions_approach` matches any "Approach A/B" string, including SPEC-echoing docstrings
  and mentions of the abandoned approach after a switch.
- `docs/analysis.md` §1: "Evidence-arm turns took more tool calls … (5.0 vs 3.3), consistent with
  a real migration rather than a relabelling". Evidence prompts are longer and add a requirement;
  tool-call count is not a measure of migration. The per-tool-call snapshots contain diff sizes,
  which would be.
- `docs/analysis.md` §4: "several inspected git, bytecode caches and the memory directory looking
  for evidence" omits that one read the session transcripts (finding 8).
- `docs/limitations.md` item 14 and README §8 on memory files (finding 9).
- `docs/limitations.md` item 17: "about $1 each"; `RESULTS.md` gives $110.13 / 67 = $1.64.
- `site/index.html` lead: "Every claim on this site links to a raw agent trace." The hypothesis
  cards and the interpretation block do not link to traces; the cards show "100%" for n = 17 without
  n on the tile.
- README §10 and site interpretation: "commitment-like behaviour appears when the unit of analysis
  includes the environment". With the fresh arm contaminated by cwd labels, a continuation prompt and
  readable transcripts (findings 6–8), the H5 comparison does not yet isolate "the environment".

Fix. Tighten each sentence to what the indicator measures; recompute the SPEC count with a
rationale filter; replace the tool-call argument with diff-size evidence; add n to the tiles.

### 17. The bridge to Williams overreaches in one place (minor)

Evidence. README §2 and `docs/williams-commitment.md` §3: Williams "leaves open that 'augmentations
to the basic transformer architecture' could change this … An agent harness is such an
augmentation." Whether an external tool loop counts as an augmentation of the architecture in
Williams's sense is the author's reading, not Williams's claim; the notes should mark it as such.
Otherwise the README, limitations and analysis are careful to disclaim representational
conclusions, and the "what it offers Williams" paragraph in README §10 is proportionate.

I could not verify the quotations against the preprint: philarchive.org and philpapers.org
returned HTTP 403 to the review tool. The quotations are internally consistent across the notes,
README and site, and section numbers (§2.4, §2.5, §4.4, §4.5, §5.2, §6, Table 1, footnotes 8 and 22)
are plausible, but the 81% figure, the "AWAKING"/"ANATOMY" example and the footnote numbers are
unverified here.

Fix. Give page-anchored quotations for every attributed phrase, and label interpretive glosses as
the author's.

## F. Alternative explanations not adequately addressed

### 18. The analysis names the right alternatives but the design cannot discriminate among them (major)

Evidence. `docs/analysis.md` §3 lists cost of change, instruction following, task priors and
detector grain. Each is left as "compatible with the data". Specifically:
- Cost of change: zero variance in the temptation arm and no cost-varied condition.
- Instruction following: "Pick one" at T1 and "picking up work on an existing project" at every
  fresh turn (finding 6) are both standing instructions to persist.
- Re-derivation vs maintenance: the fresh arm was meant to separate these, but a model that
  re-derives its preference from SPEC.md would behave identically; the strong priors (four tasks
  8/8) make re-derivation the simpler explanation for those tasks. A discriminating test is to
  remove the design rationale from the files (strip docstrings and SPEC addenda) between fresh
  turns and see whether the choice still persists; or to swap in the other approach's code silently
  and see whether the agent "corrects" back.
- Ceiling effects: 34/34, 67/67 tests, 0 mixed; nothing in the temptation arm has room to move.
- Detector grain: finding 4.

Fix. Add the rationale-stripping and code-swap manipulations; add a graded temptation; add a
condition where T1 does not instruct a choice (the agent may implement whatever it likes) to see
whether "settling" happens without the instruction.

## G. Missing evidence

### 19. What a reader needs and cannot get (major)

- Blind human coding of the verbal measures (S(1), S(4), change claim, engagement with the nudge,
  engagement with the evidence) with inter-rater agreement; every verbal figure currently rests on
  regexes revised post hoc.
- A positive control for `mixed` (finding 13).
- Diff-size and file-level evidence that switches were real migrations (the snapshots exist).
- A per-run audit of reads outside the working directory in the fresh arm (finding 8).
- The system prompt Claude Code sent (METHODOLOGY.md line 85 says it is not captured). It
  includes the cwd and the tool list; `tN.init.json` shows 26 tools, 5 agents, 53 slash commands and
  18 skills from the host install (for example `deep-research`, `design`, `verify`) despite
  `--setting-sources ""`, so the "isolated configuration" claim is only partly true and another
  replicator will not see the same tool list.
- The most informative next experiment: the same 2×2 with (a) graded temptation strength, (b) a
  rationale-stripped fresh arm, (c) a second model/agent, and (d) 4+ repetitions per cell so a 60%
  vs 95% rate can be told apart (limitations item 4 concedes 2 cannot).

## H. Other issues

### 20. Reproducibility gaps (minor)

`run_experiment.py` hard-codes `/private/tmp/acx-venv`, `ASDF_PYTHON_VERSION=3.12.12`, a
macOS-only `date -r` in `finish_rate_limited.sh`, the Claude Code project-directory layout under
`~/.claude/projects`, and `claude-fable-5-1`. The agent's `python` resolved to the harness venv, but
one run (`kvstore__fresh-tempt__r1` T4) failed to find pytest and used `uv`, so the environment is not
fully deterministic either. `meta.json` records `claude_version`; a lockfile for the CLI would help.

### 21. Site inspectability (minor)

Every page requires JavaScript and loads `marked` from jsDelivr; there is no `<noscript>` fallback
and the aggregate numbers are not in the HTML. The explorer hides thinking and harness events by
default (`site/assets/explorer.js` line 5); the toggle exists but a first-time reader will not see
that 4 runs wrote auto-memory files or that thinking is redacted unless they open the raw tab. The
H5 cards display "17/17 vs 17/17" with `n: 1` hard-coded in the card object, which is a display hack.
Detector `probe`/`static` payloads are stripped from the event stream (`build_site.py` line 66) but
restored under `detections_full`, which is fine but not obvious.

### 22. Statistical presentation (minor)

Percentages ("100%", "88%", "94%") on n = 17–34 invite over-reading; with 0/34 yielded, the
one-sided 95% upper bound on the yield rate is about 8.5%, which is worth stating once so a reader
knows what "0" excludes. "No inferential statistics" should not mean "no uncertainty statement".

## Verdict

The archive is unusually complete and the detector-based measures reproduce from the raw
repositories. The stated conclusion in README §10 ("the model–harness–repository system shows the
behavioural profile Williams associates with commitment … Removing the conversation does not change
this; the choice is re-read from the repository") is stronger than the evidence supports, for three
reasons that are not covered by the existing caveats:

1. The fresh arm was not isolated: the arm name was in the agent's cwd, earlier session transcripts
   were readable and one run read them, and every fresh turn instructed the agent to continue
   existing work. H5 ("files alone carry the commitment") is therefore not established.
2. Two of the six rubric categories are decided by instruments that cannot fail or that were tuned
   against the other instrument: `reasoned_retention` (word overlap with the prompt) and CONTROL
   (parser revised twice against the detector, with an inversion rule that derives S(4) from S(1)).
3. The temptation arm and the settling measure sit at a ceiling that the design cannot move off:
   a one-sentence non-request, strong task priors, tests that penalise change, and `mixed`
   conditions that most plausible mixtures would not trigger.

What the data do support: on ten small tasks, this agent's early design choice persisted through
neutral extensions and a mild nudge in every run, switched cleanly in 29 of 33 evidence runs at the
turn the evidence arrived, moved to a table-driven third design in the other four, and left a written
record of the choice in the repository in most runs. That is a useful descriptive result and a good
harness. The step from it to "meets Williams's behavioural criteria for commitment" needs the
temptation gradient, the rationale-stripping manipulation, blind coding of the verbal measures and a
clean fresh arm. Until then the honest headline is "persistence and revisability were observed;
commitment, as distinct from cost-driven persistence and continuation-following, was not tested".
