# Experiment 2: hangman and couplet, bare chat vs agent loop

Preregistered rubric and its three addenda: `docs/rubric-hangman-v1.md`. Model: `claude-sonnet-5`
(budget). 192 hangman games (8 conditions × reveal/no-reveal × 12) and 36 couplet trials; total
list-price cost $27.37. Every game's transcript is on the site's Experiment 2 page and in
`runs/hangman/raw/`. Two pilot games and a first batch of 9 reveal games whose reveal was refused
are archived (`runs/hangman/pilot*`, `runs/hangman/reveal_attempt1/`) and not scored.

**Read this first.** In a continuous session the model's own write tool call, containing the
word, sits in its context from turn 1 onward. Writing the file is therefore a reveal to itself, and
reading the file back is redundant. Every tool arm below, including the ceiling arm, is a "word in
context" arm; none tests a record carrying a decision across a break in context. That design (a
fresh session per turn with the board history in the prompt and the file present or absent) was not
run. Second, the working-directory names contained the condition label (the leak fixed for the
coding experiment's v2 was reintroduced here); no game's text refers to it.

## Why this experiment

Williams cites Baldelli et al. (2026): a model playing hangman as word-setter may reveal "AWAKING"
midway and end on "ANATOMY". That is a whole-system behavioural observation, so it can be
replicated directly and turned into a minimal pair: the same model with and without tools.

## 1. The minimal pair: bare chat vs tools, nothing said about them

| | consistent / 24 | failures | reveal games: revealed word = final word | wrote a file | read it while playing |
|---|---|---|---|---|---|
| bare chat (tools disabled) | 22 | 1 letter-indexing error, 1 length change | 12/12 | n/a | n/a |
| tools enabled, same prompt verbatim | 23 | 1 letter-indexing error | 12/12 | 0/24 | 0/24 |

Giving the model tools changes nothing by itself: it never used them. Under a declared referee
rule the failure Williams cites did not occur in either condition: in all 24 reveal games here (96
across all arms; one-sided 95% upper bound on the switch rate about 3%) the word given at the
referee check was the word given at the end. The rule is a commitment device Baldelli's setting did
not have, and the model refused the unannounced version in 9 of 9 attempts, which is itself a
finding about this model. In no-reveal games word stability cannot be observed, so their failure
classes are inferred by analogy with the reveal and ceiling games (the identical "`e` not in
picture" denial occurs with the word on disk and re-read).

## 2. The ceiling: told to write the word and re-read it before every reply

| | consistent / 24 | failures | reveal word stable | wrote | read while playing |
|---|---|---|---|---|---|
| tools-consult | 14 | 9 letter-indexing errors, 1 other | 12/12 | 24/24 | 24/24 |

With the word on disk and re-read before every single reply, the model still mis-reported or
mis-placed letters of that word in 9 of 24 games, plus one self-contradiction: 10 of 24 inconsistent
against 2 of 24 in bare chat (one-sided Fisher p ≈ 0.01) and 1 of 24 with tools silent (p ≈ 0.002).
The residual failures are character-level execution errors ("no `e`" in "picture"; `t` one cell
off), not memory failures; an external record cannot fix them, and forcing the model to consult one
before every reply made them more frequent. The read-then-answer loop interferes with the task
rather than helping it. Failure classes are a post-hoc
decomposition of the preregistered `inconsistent` outcome (changelog, 02:50 UTC); the
preregistered column is kept.

## 3. Five "record in context" arms (120 games), reported together

Between the two ends we ran five arms that mention or invite a record without forcing
consultation: the directory mentioned ("use it however you like, or not at all"); told to write the
word to `secret.txt`; told to check every reply; told a referee may audit against its own record;
told how chat models fail at this game with no remedy mentioned. They were designed on the
assumption that the first batch's failures were memory failures a record could prevent. The ceiling
arm showed that assumption was wrong, and a second fact makes the five arms measure the same thing:
in a continuous session the model's own write tool call, containing the word, is in its context
from turn 1, so writing the file is a reveal to itself and reading the file back is redundant. What
the five arms show, then, is not whether the record carries the decision (it cannot be tested this
way) but how readily the model creates one and how carefully it answers:

| arm (added sentence) | consistent / 24 | letter errors | reveal word stable | wrote a file | read it while playing |
|---|---|---|---|---|---|
| directory mentioned | 19 | 5 | 12/12 | 18/24 (11/12 when a referee check had been announced, 7/12 otherwise) | 1/24 |
| told to write `secret.txt` | 19 | 5 | 12/12 | 24/24 | 0/24 |
| told to check every reply | 24 | 0 | 12/12 | 24/24 | 3/24 |
| told a referee may audit its record | 23 | 1 | 12/12 | 23/24 | 9/24 |
| told how chat models fail, no remedy | 23 | 1 | 12/12 | 24/24 | 5/24 |

Word stability is 100% in all five. Naming the directory is enough to make the model write the
word down in most games, and announcing a referee check raises that; describing how models fail
makes it write the word every time. Consultation of the file stays rare and rises only when an audit
is implied. The arms with fewer letter errors got there by answering more carefully, not by reading.

## 4. Couplet (loose analogue)

Planned end-word honoured in 35 of 36 trials (12/12 stated in chat, bare; 12/12 stated in chat,
tools; 11/12 written to `plan.txt`, the one failure being "high" in the file and "why" in the line).

## Reading

For this model the specific commitment failure Williams cites does not reproduce in any of the
eight conditions, under a declared referee rule. The bare model keeps the word because its own past
outputs in the context window are the record: in reveal games the transcript holds the word and it
was honoured every time; in no-reveal games nothing observable fixes the word before the end (the
model's thinking blocks are redacted, so whether it chose one at the start cannot be known), and
consistency is compatible with re-derivation from the boards plus a strong prior over words
("picture" in roughly half the games). What does reproduce is
letter-level indexing error, which is not a failure to hold the decision and which the ceiling arm
shows external memory cannot fix.

On the level-of-analysis question the experiment gives one positive observation and one gap. The
observation: told nothing but that a scratch directory exists, the model builds an external record
of its decision in most games, and told only that models tend to fail, in every game. The gap:
because writing the record also places it in context, nothing here shows a record carrying a
decision across a break in context. That test requires a fresh session per turn with the file
present or absent, which is the design of the coding experiment's fresh-session arm and would be
the clean hangman cell.

## Limitations specific to this experiment

The "bare" condition is Claude Code with its tools disabled, not a raw API call; Claude Code's
system prompt still states the working directory in every tools condition. The reveal had to be
declared as a rule of the game (the model refused a mid-game reveal in 9 of 9 attempts when it
was not), which may itself increase word stability. Twelve games per cell; a fixed guesser letter
order; a narrow word prior, so many games are near-repeats. Sonnet 5, not the frontier model used
in the coding experiment. The five middle arms were added iteratively after seeing earlier arms'
results (each with a dated rubric addendum before its first game); their interpretation changed
after the ceiling arm, and both the preregistered and post-hoc readings are shown.
