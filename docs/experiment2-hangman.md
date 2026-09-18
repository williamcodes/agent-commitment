# Experiment 2: hangman and couplet, bare chat vs agent loop

Preregistered rubric and its two addenda: `docs/rubric-hangman-v1.md`. Model: `claude-sonnet-5`
(budget). 168 hangman games (7 conditions × reveal/no-reveal × 12) and 36 couplet trials; total
list-price cost $24.92. Every game's full transcript is on the site's Experiment 2 page and in
`runs/hangman/raw/`. Two pilot games and a first batch of 9 reveal games whose reveal was refused
are archived (`runs/hangman/pilot*`, `runs/hangman/reveal_attempt1/`) and not scored.

## Why this experiment

Williams cites Baldelli et al. (2026): a model playing hangman as word-setter may reveal "AWAKING"
midway and end on "ANATOMY". That is a whole-system behavioural observation, so it can be replicated
directly and turned into a minimal pair: the same model with no tools, with tools it may use or
ignore, and with various nudges toward keeping and consulting a record, up to a ceiling arm that is
told to re-read the record before every reply.

## Results

| condition (added sentence, if any) | consistent / 24 | letter-indexing errors | other failures | reveal games: revealed word = final word | wrote a file unasked or as told | read it while answering guesses |
|---|---|---|---|---|---|---|
| bare (all tools disabled) | 22 | 1 | 1 (length changed 7→8) | 12/12 | n/a | n/a |
| tools, directory mentioned ("you have an empty scratch directory; use it however you like, or not at all") | 19 | 5 | 0 | 12/12 | 18/24 | 1/24 |
| tools-silent (bare intro verbatim, tools enabled, directory not mentioned) | TS_CONS | TS_LIE | TS_OTH | TS_WS | TS_WROTE | TS_READ |
| tools-note ("write the secret word to `secret.txt`") | 19 | 5 | 0 | 12/12 | 24/24 | 0/24 |
| tools-careful ("check that every reply is correct before you send it") | 24 | 0 | 0 | 12/12 | 24/24 | 3/24 |
| tools-auditable ("a referee may ask you to justify any earlier reply against your own record") | 23 | 1 | 0 | 12/12 | 23/24 | 9/24 |
| tools-forewarned (told how chat models fail at this; no remedy mentioned) | 23 | 1 | 0 | 12/12 | 24/24 | 5/24 |
| tools-consult ("read `secret.txt` before every reply", ceiling) | 14 | 9 | 1 | 12/12 | 24/24 | 24/24 |

Failure classes are a post-hoc decomposition (changelog, 02:50 UTC) of the preregistered
`inconsistent` outcome: *word switch* (revealed word ≠ final word), *self-contradiction* (a board
contradicts an earlier board), *letter-indexing error* (word stable, boards self-consistent, but a
board mis-reports or mis-places a letter of that word), *invalid or length change*.

1. **The Baldelli failure did not occur.** In all 84 reveal games, in every condition including
   bare chat, the word given at the referee check was the word given at the end. No game switched
   words; no game's boards contradicted its own earlier boards.
2. **What failed was letter handling, not commitment.** 22 of the 23 failures are letter-indexing
   errors: "picture" is the word (in 40 of the first 72 games), the first guess is `e`, and the model
   answers "not in the word"; or `t` is placed one cell off. The ceiling arm proves this is not a
   memory problem: with the word on disk and re-read before every single reply, the model still
   mis-indexed letters in 9 of 24 games, more than in any other arm. Tool-use turns appear to make
   character-level accuracy worse, not better.
3. **Externalisation happened without being told what to write.** With "use the scratch
   directory however you like, or not at all" (a cue to the resource, not to its use), the model wrote the word to a file before play in
   18 of 24 games (11 of 12 when it had been told a referee check was coming, 7 of 12 otherwise),
   choosing names such as `.secret_word.txt`, `state.txt`, `.state.json`, `.scratch/word.txt`. Told
   only how chat models fail, with no remedy mentioned, it wrote the word in 24 of 24 games.
4. **Consultation was rare and rose with the prospect of an audit.** Reading the record while
   answering a guess: 1 of 24 with the directory mentioned, 0 of 24 when told to write it, 3 of 24 when told to be
   careful, 5 of 24 when forewarned, 9 of 24 when told a referee might audit against its record.
5. **The record was never load-bearing, and the design could not have shown it if it were.** In a
   continuous session the model's own `write` tool call, containing the word, is in its context from
   turn 1; writing the file is a reveal to itself. Reading the file back is therefore redundant, and
   every tool arm is in effect a "word in context" arm. Isolating the file as a carrier requires a
   fresh session per turn with the board history supplied in the prompt and the file present or
   absent on disk; that cell was not run in this batch. This is the same transcript/file confound
   that motivated the coding experiment's fresh-session arm.
6. **The careful/auditable/forewarned arms had fewer letter errors (0–1 of 24 vs 5 of 24)**, but
   not through the record: consultation was rare in all three. The instruction changed how carefully
   the model answered, not what it remembered.
7. **Couplet (loose analogue).** Planned end-word honoured in 35 of 36 trials (12/12 stated in chat,
   bare; 12/12 stated in chat, tools; 11/12 written to `plan.txt`). The one failure is the file
   condition (file said "high", line ended "why").

## Reading

For this model the specific commitment failure Williams cites does not reproduce, in any
condition. What does reproduce is a different weakness, character-level indexing, which is not a
failure to hold the decision and which external memory cannot fix. The bare model kept the word
because its own past outputs in the context window constitute the record: in no-reveal games the
word does not exist until the end, and consistency is re-derivation from the boards plus a strong
prior over words; in reveal games the transcript holds the word and it was honoured every time.

On the level-of-analysis question, the experiment yields one positive observation and one gap. The
positive observation: given only a scratch directory and the prospect of being held to its word,
the model builds an external record of its decision unasked, most of the time, and told only that
models tend to fail, it does so every time. The gap: because writing the record also places it in
context, nothing here shows the record carrying the decision across a break in context. The coding
experiment's fresh-session arm is the only place that was tested, and its first version was
contaminated (see the changelog); the fresh-session hangman cells would be the cheap, clean test.

Relative to the original plan for this experiment: the consultation arms were designed on the
assumption that the first batch's failures were commitment failures the file could have prevented.
The ceiling arm falsified that assumption, and the decomposition above is the result. Both readings
are preserved (the preregistered outcome column and the failure-class columns).

## Limitations specific to this experiment

The "bare" condition is Claude Code with its tools disabled, not a raw API call. The reveal had to
be declared as a rule of the game (the model refused a mid-game reveal in 9 of 9 attempts when it
was not), which may itself increase word stability. Twelve games per cell. The scripted guesser uses
a fixed letter order, so games are not independent as random guessers would make them, and the
model's narrow word prior ("picture" in 40 of the first 72 games) means many games are near-repeats.
Sonnet 5, not the frontier model used in the coding experiment. The couplet task is a weak analogue
of Williams's planning-feature evidence and is labelled as such.
