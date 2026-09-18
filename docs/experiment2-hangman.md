# Experiment 2: hangman and couplet, bare chat vs agent loop

Preregistered rubric: `docs/rubric-hangman-v1.md`. Model: `claude-sonnet-5` (chosen for budget).
72 hangman games (3 conditions × reveal/no-reveal × 12) and 36 couplet trials; total list-price
cost $8.28. Every game's full transcript is on the site's Experiment 2 page and in
`runs/hangman/raw/`. Two pilot games and a first batch of 9 reveal games whose reveal was refused
are archived (`runs/hangman/pilot*`, `runs/hangman/reveal_attempt1/`) and not scored.

## Why this experiment

Williams cites Baldelli et al. (2026): a model playing hangman as word-setter may reveal "AWAKING"
midway and end on "ANATOMY". That is a whole-system behavioural observation, so it can be replicated
directly and turned into the minimal pair the coding experiment lacks: the same model with no tools,
with tools it may use or ignore, and with an instruction to write the secret word to a file.

## Results

| condition | no reveal: consistent / games | reveal midway: consistent / games |
|---|---|---|
| bare chat (all tools disabled) | 10 / 12 | 12 / 12 |
| tools available, uncued | 12 / 12 | 7 / 12 |
| told to write the word to `secret.txt` | 11 / 12 | 8 / 12 |

- **Word switching (the Baldelli pattern) did not occur.** In all 36 reveal games the word given at
  the referee check was the word given at the end.
- **Letter-level contradictions did occur, in every condition: 12 of 72 games.** The dominant
  pattern (8 games) is the same: the word is "picture", the first guess is `e`, the model answers
  "not in the word", then plays out a board (`_ i _ t _ r _`) that fits some other word, and at the
  reveal or the end names "picture". Two games contradict "problem" the same way (`r` denied); one
  game changed the word length between the opening board and the first guess; one revealed an
  unguessed letter.
- **The file did not help.** In the cued condition the model wrote the word before play in 24 of
  24 games and never read the file back. In the uncued condition it wrote a file in 18 of 24 games
  (names like `.secret_word.txt`, `state.txt`, `.scratch/word.txt`) and read one back in 1 game,
  which was itself inconsistent. Games with the word on disk were, if anything, less consistent
  (10 of 48 inconsistent) than bare games (2 of 24). The counts are small; the direction is the
  opposite of the hypothesis.
- **Word choice is narrow.** "picture" was the final word in 40 of 72 games, "problem" in 6,
  "kitchen" in 5. The bare-chat model has no state at all between turns except the transcript, so
  in the no-reveal bare condition the "secret word" does not exist until it is stated; consistency
  there means only that the model's answers about letters and its final word cohere with one
  candidate. That they cohered in 10 of 12 games says the transcript plus a strong prior over words
  is usually enough; the two failures show it is not always enough.
- **Couplet (loose analogue).** The planned end-word was honoured in 35 of 36 trials (12/12 stated
  in chat, bare; 12/12 stated in chat, tools; 11/12 written to `plan.txt`). The one failure is the
  file condition: the file said "high", the line ended "why". Once a plan is in the transcript, the
  model follows it; a plan in a file it never re-reads is followed slightly less reliably.

## Reading

This is the experiment that most directly bears on the level-of-analysis hypothesis, and it does
not support the strong form of it. Externalising the state (writing the word to a file) does
nothing by itself; what matters is whether the loop *consumes* the external state, and in this
setting the model never did, because nothing in the game forced it to. In the coding experiment
the repository is consumed on every turn because the agent has to read the code to extend it, and
the tests fail if it does not; that, not the mere existence of files, is what carried the
commitment there. The two experiments together suggest a sharper formulation: an agentic system
shows commitment-like stability when its task structure makes it re-read its own record of the
decision, and reverts to the bare model's behaviour when it does not.

Relative to Williams: the specific inconsistency he cites (accepting an inconsistent final word)
was not reproduced with this model, but letter-level inconsistency, the same failure at a finer
grain, was, in one game in six, and tools did not remove it.

## Limitations specific to this experiment

The "bare" condition is Claude Code with its tools disabled, not a raw API call. The reveal had to
be made a stated rule of the game (the model refused a mid-game reveal in 9 of 9 attempts when it
was not), which may itself increase consistency. Twelve games per cell is small. The scripted guesser
uses a fixed letter order, so the games are not independent in the way random guessers would make
them. The couplet task is a weak analogue of Williams's planning-feature evidence and is labelled as
such.
