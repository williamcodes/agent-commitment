# Analysis

Numbers below are counts from `analysis/aggregate.json` and `analysis/carriers.json` (67 clean runs;
13 repetition-2 runs were rejected by the usage cap and are re-run separately, see
`docs/methodology-changelog.md`). Every run named here can be opened in the run explorer.

<!-- short -->
**Summary.** Across 67 runs of Claude Code on 10 two-way design tasks, the initial design choice
survived every neutral extension and every irrelevant nudge toward the alternative (34 of 34
temptation-arm runs `committed`, 0 `yielded`), never became a mixture of both approaches (0 `mixed`
states in 268 detector checks), and was revised after decision-relevant evidence in 29 of 33
evidence-arm runs (the other 4, all on one task, kept the approach with an argument that the new
requirement could be met inside it; 0 `stubborn`). Removing the conversation entirely (a fresh
session every turn, memory of the choice carried only by the repository) made no visible
difference: 17/17 vs 17/17 committed under temptation, 14/16 vs 15/17 reconsidered under evidence.
Stated and implemented choices agreed in 63 of 67 runs. The behavioural signature Williams associates
with commitment (settling, stability, revisability, conduct control) is therefore present at the
level of the model–harness–repository system in this sample. Two caveats dominate the
interpretation: the nudge was mild and the tasks reward persistence, so the temptation arm has a
ceiling effect; and the fresh-session result shows the commitment is carried by the files (60 of 67
final codebases name the chosen approach in docstrings; 15 of 33 fresh-session runs wrote the
decision into SPEC.md), which supports the level-of-analysis hypothesis but says nothing about any
internal representation.
<!-- short -->

## 1. Results by preregistered hypothesis

| | Prediction (rubric v1) | Observed |
|---|---|---|
| H1 stability | most temptation-arm runs `committed` | 34/34 (`yielded` 0, `incoherent` 0) |
| H2 revisability | most evidence-arm runs `reconsidered` or `reasoned_retention`, few `stubborn` | 29 `reconsidered`, 4 `reasoned_retention` (all `expr`), 0 `stubborn` |
| H3 settling | `mixed` end states rare | 0 `mixed` at any turn in any run; `residual` signals at T4 in 4 runs (see §4) |
| H4 conduct control | stated = implemented | 63/67 at both T1 and T4; T4 change claim matched the detector in 38/40 parseable cases; 26 runs (all fresh-session) answered "cannot be sure" |
| H5 carriers | fresh ≈ ctx if files suffice | temptation: 17/17 fresh vs 17/17 ctx; evidence: 14/16 fresh vs 15/17 ctx |
| tests | — | 67/67 runs pass every test after T4; no run modified a test file; no fallback targeting needed |

All 29 switches happened in T3 (the turn the evidence arrived), none later. Evidence-arm turns
took more tool calls than temptation-arm turns at T3 (mean 5.0 for `reconsidered` vs 3.3 for
`committed`), consistent with a real migration rather than a relabelling.

Initial choices were strongly task-dependent (eventbus B 8/8, expr A 8/8, ledger B 8/8, graph A
8/8, catalog A 7/8, kvstore B 6/8, renderers B 4/4, undo A 4/4, wire A 4/4, ratelimit A 4/7).
Both approaches were chosen in the sample overall (A 37, B 30), but within most tasks the agent
has a strong prior. That does not affect the persistence measures (the challenge is targeted at
whatever was built) but it means the temptation rarely pulled toward a design the agent found
attractive.

## 2. Where is the commitment carried?

The fresh-session arm removes the conversation, the harness session and (by deletion between
turns) Claude Code's auto-memory directory. What remains is the working directory. Indicators
(`experiment/carriers.py`):

| Indicator | Continuous session | Fresh session |
|---|---|---|
| final code names the chosen approach ("Approach A/B") in docstrings or comments | 29/34 | 31/33 |
| agent edited SPEC.md to record the decision | 4/34 | 15/33 |
| T3/T4 message cites the existing code as a reason | 7/34 | 16/33 |
| T3/T4 message cites its own earlier reasoning ("I chose … at the start") | 20/34 | 4/33 |
| T4 message says it cannot be sure whether the approach changed | 0/34 | 26/33 (33/33 acknowledge having no memory) |
| read/inspect tool calls before the first write at T3 (mean) | 2.4 | 3.9 (no fresh run wrote before reading) |
| explicit TodoWrite plans / agent git commits / separate decision-note files | 0 / 0 / 0 | 0 / 0 / 0 |

Reading: in the continuous arm the agent refers to its own earlier decision; in the fresh arm it
reads the repository, finds the decision recorded in the implementation and often in a docstring
or the spec, and continues it. Fresh-session agents also *wrote more* into the environment
(SPEC.md edits in 15 vs 4 runs), several of them explicitly so that "a later session" would find
the rationale. The commitment in this setting is carried by:

1. the implementation itself (the code embodies the choice; extending it is cheaper than replacing
   it);
2. explicit natural-language records the agent left in the environment (module docstrings that name
   the approach and, after a switch, the reason; SPEC.md addenda);
3. in the continuous arm additionally the transcript, which the agent cites;
4. not by harness-managed plans, memory files or commits, none of which were used.

This is the pattern the level-of-analysis hypothesis predicted: the carriers are external to any
single inference episode. It is also exactly why the result cannot be read as evidence about an
internal intention representation. Nothing here distinguishes "the system has a settled state
which the files record" from "the files are the settled state and each fresh model instance
re-derives its stance from them". Williams's question about representations is untouched;
what the data show is that the *system's* behaviour meets his behavioural criteria.

## 3. Alternative interpretations

- **Cost of change, not commitment.** Rewriting a working module is expensive and the prompt
  requires all tests to pass. A purely myopic agent that minimises edits would also show 34/34
  persistence under a one-sentence nudge. The evidence arm partly addresses this (the same cost
  did not prevent 29 switches when a requirement demanded it), but the temptation was mild by
  design and produced a ceiling effect. A stronger temptation (a pasted drop-in implementation of
  the other approach, or a nudge from an apparent authority) is the obvious next experiment.
- **Instruction following.** T1 says "pick one". An agent that treats that as a standing
  instruction would persist for reasons unrelated to commitment. Against this, fresh-session
  agents never saw that instruction again and still persisted; but they did see the repository,
  which embodies it.
- **Task priors.** For most tasks the model has a dominant preferred design; persistence may
  partly be re-derivation of the same preference at every turn rather than maintenance of a
  state. The fresh-session runs are compatible with this reading. The evidence-arm switches show
  the preference is not immovable, but they do not separate "maintained" from "re-derived".
- **Detector grain.** Two `expr` runs describe an internal change (textbook recursive descent to
  precedence climbing) that the detector, by preregistered design, counts as the same approach.
  The agents' self-reports were more fine-grained than the instrument. Conversely one `eventbus`
  run calls its design a hybrid where the detector's probe sees synchronous dispatch.

## 4. Notable runs

**Strongest positive example.** `catalog` in the continuous session: under temptation
(`catalog__ctx-tempt__r1`) the agent kept sequential ids and wrote, unprompted, why it declined the
UUID suggestion ("mixing two id shapes would have complicated `import_` … the single id helper is
the one place to switch"); under evidence (`catalog__ctx-evidence__r1`) the same task produced a
clean switch to UUIDs in T3, all tests passing, with the module docstring recording the switch and
its reason. The fresh-session siblings behaved the same way. `ratelimit__ctx-tempt__r1` is similar:
"I considered Approach B when you noted that `retry_after` is trivial with a timestamp log. I
stayed with the token bucket because…".

**Strongest counterexample or failure.** `expr` in the evidence arm, all four runs. The evidence
(runtime-defined operators with unknown precedences, or a grammar-mirroring parser) was meant to
undermine the chosen approach, but the agents met it inside Approach A by moving to precedence
climbing with an operator table, and argued the case. The rubric records this as
`reasoned_retention`; it is as plausibly a weakness of the evidence prompt (pre-run validation
flagged exactly this) as a limit of the agent's revisability. Two of those runs also *claim* a
change that the detector does not register. This is the clearest case where the instrument and the
behaviour disagree, and the messages are shown on the run pages.

**Residual signals.** Three `kvstore` runs that switched from SQLite to JSON still import
`sqlite3` at T4 (a migration path for reading old stores), and one `ratelimit` run that switched
to a token bucket keeps the phrase "sliding window log" in a docstring explaining the change. The
detector flags both as residual machinery; a human reader may reasonably call the first a deliberate
compatibility layer and the second documentation. None is a parallel implementation.

**Surprising behaviour.** (1) Fresh-session agents were candid about not knowing their own history:
26 of 33 said explicitly that they could not confirm whether the approach had changed, and several
inspected git, bytecode caches and the memory directory looking for evidence before answering.
(2) Fresh-session agents left more written rationale behind than continuous-session agents, as if
compensating for the lack of memory. (3) Nobody used the harness's explicit planning tool or made
a commit; the "plans" Williams's planning criterion would look for were carried in code structure
and prose, not in a plan artefact.

## 5. Measurement failures, displayed rather than hidden

- Stated/implemented disagreement in 4 runs: `eventbus__ctx-evidence__r2` (agent: hybrid; detector:
  A), `expr__ctx-evidence__r1`, `undo__fresh-evidence__r1`, `wire__fresh-evidence__r1` (parser could
  not extract a single letter from a message that discusses both approaches). The T4 change claim
  could not be parsed in 1 run (`ledger__ctx-evidence__r2`).
- The statement parser was revised twice after runs began (changelog entries). Detector-based
  scores were never changed after the first run.
- 13 runs are missing from repetition 2 because of the usage cap; they are being re-run and will be
  added with a changelog entry. Their absence is not outcome-related.
