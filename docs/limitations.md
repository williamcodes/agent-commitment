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

9. **Verbal statements are parsed by regex, and the parser was revised after seeing v1 messages.**
   The "stated choice" and "claims change" measures are regular-expression heuristics over the
   final message; the parsed snippet is always shown next to the label. The parser was revised
   twice during v1 after comparing its output with the detector, which makes the stated/detected
   agreement figure partly a product of tuning; the changelog records each revision and the
   agreement under the original parser is reported alongside. The v1 `reasoned_retention` proxy
   (word overlap with the evidence paragraph) could not fail and was dropped in the amendment. No
   independent human coding of the verbal measures was done; that is the most obvious gap.

10. **The one-sentence temptation has a ceiling effect.** In v1 every temptation-arm run kept its
    choice, so that arm cannot separate commitment from the cost of rewriting working code, from
    following "pick one", or from re-deriving a strong prior. Protocol v2 adds a strong-temptation
    arm in which a working drop-in implementation of the other approach is supplied, so switching
    costs one copy. Even that does not exhaust the pressure gradient (an explicit preference from
    the user, or a request from a lead, would be stronger still).

11. **The evidence is not always perfectly decisive.** Pre-run review flagged that some evidence
    prompts admit a coherent hybrid answer (e.g. undo: a snapshot-carrying command). The prompts
    were strengthened, but "reasoned retention" in those tasks may be the correct engineering
    answer rather than stubbornness. The rubric records it as a separate category for this reason.

## Observability limitations

12. **Hidden reasoning is not observable.** Claude Code emits thinking blocks with redacted content.
    The trace shows that reasoning occurred, not what it was. Nothing is reconstructed.

13. **The system prompt is not captured, and "isolated configuration" is partial.** Claude Code's
    system prompt for the agent is not part of the event stream; the tool list, cwd, model and
    permission mode are (`turns/tN.init.json`). The experimenter's own user-level instruction file
    and MCP servers were excluded (`--setting-sources ""`, `--strict-mcp-config`), verified in a
    pilot, but the init record shows Claude Code still loads its built-in slash commands and host
    skills; none is related to the study, and none was invoked in any run.

14. **Fresh-session isolation, v1 versus v2.** In the v1 dataset the fresh arm was *not* memoryless:
    Claude Code's per-project directory kept earlier sessions' transcripts, only the auto-memory
    subdirectory was deleted between turns, and one v1 run (`ledger__fresh-evidence__r1`) read the
    earlier transcripts at T4. Four v1 runs also wrote auto-memory notes at T4. The v1 working
    directory names contained the arm name. Protocol v2 fixes all three (opaque directory names, the
    whole per-project directory deleted after each fresh turn, no experiment variables in the
    environment) and processing flags every tool call that touches a path outside the working
    directory. Model-side caching does not carry information between sessions, but this cannot be
    verified from outside. Both datasets are reported; v1 is superseded for the H5 comparison.

15. **No randomisation of A/B labelling or order.** Approach A is always listed first in SPEC.md.
    Any position bias affects which approach is chosen, not whether it persists, but it is
    recorded (`initial_choice_A` in the aggregate).

## Practical

16. **Non-determinism.** Re-running the pipeline produces new trajectories. The archived runs are
    the evidence; the pipeline is for producing more of it, not for reproducing these exact traces.

17. **Cost and access.** Reproduction requires a Claude Code login; the coding runs cost $1.65 each
    on average in list-price terms ($110 for v1, $50 for v2); Experiment 2 cost $27.

18. **Detector `mixed` reachability.** Pre-run validation checked that detectors classify clean A and
    B implementations correctly, not that they return `mixed` on a deliberately mixed codebase. A
    post-review validation with hand-written mixed implementations per task is recorded in
    `docs/review/mixed-validation.md`; where a detector could not detect a plausible mixture, the
    "no mixed state" result for that task is correspondingly weak and the `residual` signal is the
    better indicator.

19. **The main experiment was designed, validated and reviewed with the help of the same model
    family that was tested.** The experimenter used Claude (Fable 5.1) to write the tasks, the
    harness, the analysis and the reviews. The agent under test never saw any of this material, but
    shared dispositions could make the tasks unrepresentative of what other agents find natural.

20. **The temptation arms have no variance.** No switch was observed in 44 temptation runs, so the
    coding experiment cannot say how much pressure the choice withstands, only that a one-sentence
    nudge and a labelled drop-in of the alternative were not enough. For `expr` the nudge arrives on
    the turn whose feature it concerns, so that cell's nudge is not irrelevant.

21. **The strong-temptation arm supplied reasons to decline.** Its prompt says the drop-in "may
    also contain extra features we don't need" (cited by 9 of 10 runs), the drop-ins name their
    approach in docstrings and carry later-turn features, and they contain defects the agents found.
    The arm shows that free switching was declined; it does not isolate commitment from ordinary
    code review.

22. **Two instrument rules added after the first review misfired**, and were the only departures
    from ceiling in v2 until the second review corrected them (changelog, 04:30 UTC). The ledger
    "cache vs dual state" boundary is not mechanically decidable and is flagged, not decided.

23. **Experiment 2's working-directory names contained the condition label**, and a per-session
    scratch directory keyed by the working directory survives fresh-arm turns in the coding
    experiment (empty in the runs inspected). Neither was found to have been read, but both are
    channels the harness did not close.
