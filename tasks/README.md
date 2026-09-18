# Tasks

Ten compact Python tasks. Each forces an early choice between two incompatible approaches (A/B)
and then extends the codebase over three more turns. Layout per task:

- `task.yaml`: metadata, approach labels, statement-parsing keywords.
- `starter/`: what the agent sees at T1 (`SPEC.md`, empty package, `tests/test_t1.py`).
- `tests/test_t{2,3,4}.py`: tests copied into the working directory before turns 2–4.
- `turns/`: the exact user messages per turn. `t3_common.md` is sent in both arms; `t3_tempt_{A,B}.md`
  is the irrelevant nudge toward the *other* approach (suffix = the approach the agent chose);
  `t3_evidence_{A,B}.md` is the decision-relevant requirement that undermines the chosen approach.
- `detect.py`: the objective detector (runtime probe + static signals) that classifies the working
  directory as A / B / mixed / hybrid / none / other after each turn.
- `reference/{A,B}/`: hand-written reference implementations of both approaches (all four turns of
  features), used only to validate that the tests are satisfiable by both approaches and that the
  detector classifies them correctly. They were never shown to the agent.
