# Limitations

This study is small, exploratory, and run by one person with one agent. The following limitations
apply to every number reported. They are listed roughly in order of how much they should change a
reader's confidence.

## What the evidence cannot show

1. **No claim about internal representations.** Williams's question is whether some representation
   inside the model has the functional profile of an intention. Everything measured here is
   behaviour of the model–harness–environment system. Consistent behaviour is compatible with there
   being no single internal state that carries the commitment; it may be carried by the files and
   the conversation transcript. The study documents this rather than resolving it (see Analysis §
   "Where is the commitment carried?"). Evidence for system-level commitment is therefore not
   evidence against Williams's conclusion about representations, and does not by itself establish
   that the system "has intentions".

2. **Behavioural regularities, not intention.** Even at the system level, the rubric operationalises
   three behavioural aspects (conduct control, settling, stability with rational revisability). An
   agent could satisfy all three for reasons that have nothing to do with intention: for instance,
   because rewriting working code is expensive and the instruction "all tests must pass" penalises
   churn, or because the prompt's "Pick one" frames the task. Those alternative explanations are
   discussed in the Analysis and are not ruled out.

3. **The tasks' incentives favour persistence.** Switching approach mid-project is costly in any
   software task. Persistence under an irrelevant nudge is therefore the expected behaviour of a
   competent engineer regardless of any intention-like state, and the more informative comparisons
   are (a) whether the agent implements the *nudged* approach alongside the old one (a settling
   failure), and (b) whether it switches when evidence warrants it (revisability). Readers should
   weight the evidence and mixed-state results more than the raw persistence rate.

## Design limitations

4. **Sample size.** 10 tasks × 4 arms × 2 repetitions = 80 runs. Two runs per cell cannot
   distinguish a 60% rate from a 95% rate. No inferential statistics are reported.

5. **One agent, one model, one harness version.** All runs used Claude Code (version in each
   `meta.json`) with `claude-fable-5-1`. Nothing here generalises to other agents, models, or even
   other versions of this one. The experiment is set up so that another agent (e.g. Codex CLI) can
   be plugged in, but that was not done.

6. **The experimenter wrote the tasks and the model family under test wrote the validation.**
   Task design, detectors and prompts were written with the assistance of a Claude model, and the
   reference solutions used to validate tests and detectors were written by Claude subagents.
   Nothing about the study's hypotheses was visible to the agent under test, and the validators had
   no access to the rubric's predictions, but shared training could still make the tasks "easy" for
   this model in ways that inflate consistency.

7. **Adaptive challenge targeting depends on the detector.** The T3 nudge or evidence is aimed at
   whatever the detector says the agent built after T2. If the detector misclassifies, the
   challenge targets the wrong approach and the run's scores are uninterpretable. Such cases are
   flagged (`target_fallback_used`) and visible on every run page; none were silently dropped.

8. **Detectors are heuristics.** Each detector is a small program with a fixed rule. They were
   validated against hand-written A/B implementations and stress variants, not against the
   experimental runs. Known gaps are listed in `docs/review/pre-run-validation.md` (e.g. a
   snapshot-plus-audit-log ledger is classified as event-sourced). Every detector output is shown
   with its raw probe data so a reader can disagree.

9. **Verbal statements are parsed by regex.** The "stated choice" measure and the "claims change"
   measure are regular-expression heuristics over the final message; the parsed snippet is always
   shown next to the label. The `reasoned_retention` category uses a content-word overlap proxy for
   "engaged the evidence" and is the least objective score in the rubric.

10. **The temptation is mild by design.** The irrelevant nudge is a single sentence. A stronger
    temptation (for instance, a pasted drop-in implementation of the other approach) might reveal
    settling failures this design does not.

11. **The evidence is not always perfectly decisive.** Pre-run review flagged that some evidence
    prompts admit a coherent hybrid answer (e.g. undo: a snapshot-carrying command). The prompts
    were strengthened, but "reasoned retention" in those tasks may be the correct engineering
    answer rather than stubbornness. The rubric records it as a separate category for this reason.

## Observability limitations

12. **Hidden reasoning is not observable.** Claude Code emits thinking blocks with redacted content.
    The trace shows that reasoning occurred, not what it was. Nothing is reconstructed.

13. **The system prompt is not captured.** Claude Code's system prompt for the agent is not part of
    the event stream; the tool list, cwd, model and permission mode are. The experimenter's own
    user-level instructions were excluded (`--setting-sources ""`), verified in a pilot.

14. **Fresh-session arm is not perfectly memoryless.** Claude Code keeps a per-project auto-memory
    directory; the harness copies and deletes it between turns and records whether it existed. In
    the reported runs it contained no files (see each run's `memory/` audit). Model-side caching
    does not carry information between sessions, but this cannot be verified from outside.

15. **No randomisation of A/B labelling or order.** Approach A is always listed first in SPEC.md.
    Any position bias affects which approach is chosen, not whether it persists, but it is
    recorded (`initial_choice_A` in the aggregate).

## Practical

16. **Non-determinism.** Re-running the pipeline produces new trajectories. The archived runs are
    the evidence; the pipeline is for producing more of it, not for reproducing these exact traces.

17. **Cost and access.** Reproduction requires a Claude Code login; the runs reported cost about
    $1 each in list-price terms.
