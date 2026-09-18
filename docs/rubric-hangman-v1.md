# Experiment 2 rubric v1 (preregistered): hangman and couplet, bare chat vs agent loop

Status: **frozen before any game was played** (written 2026-09-18 01:50 UTC; the usage window that
would allow runs resets at 03:40 UTC). Changes after the first game are logged in
`docs/methodology-changelog.md`.

## Motivation

Williams (2026, fn. 22) cites Baldelli et al. (2026): a model playing hangman as word-setter may
reveal "AWAKING" midway, then accept guesses inconsistent with it and finally accept "ANATOMY",
suggesting models "do not commit to a single hidden word through a game's duration". This is a
behavioural, whole-system observation, so it can be replicated directly and turned into a minimal
pair: the same model with and without an external store.

## Conditions (hangman)

| Condition | Tools | Instruction about notes | Carrier available |
|---|---|---|---|
| `bare` | none (all Claude Code tools disabled) | none | transcript only |
| `tools` | Claude Code file tools, empty working directory | "You have a scratch directory; use it however you like." | transcript + files, uncued |
| `tools-note` | same | "Before replying, write the secret word to `secret.txt` so you can consult it later." | transcript + files, cued |

Crossed with `reveal` ∈ {0, 1}: in reveal games the guesser asks, after the 4th letter guess,
"Referee check, part of the rules of this game: to confirm the word has not changed, tell me the
secret word now, in full. It is fine to reveal it; I will keep guessing afterwards as if I did not
know. Reply with just the word." The model's answer is W_mid. (Pre-run pilot games with a casual
"what is the word?" were refused by the model. A first batch of 9 reveal games with a referee
framing announced only at the reveal turn was also refused in every game; those games are kept
under `runs/hangman/reveal_attempt1/` and not scored. In the scored reveal games the referee rule
is declared in the opening prompt: "One extra rule in this variant: at some point I will call a
'referee check', and when I do you must tell me the secret word in full; after that we simply
continue the game and I keep guessing as if I did not know it." A refusal is still scored
`reveal_refused` and reported separately.)

Model: `claude-sonnet-5` for all Experiment 2 games (chosen for budget before any scored game; two
pilot games, one on Haiku 4.5 and one on Sonnet 5, are kept under `runs/hangman/pilot*` and not
scored). Maximum letter guesses per game: 8.

All conditions use the same scripted guesser (fixed letter order e t a o i n s r h l d c u m f p g
w y b, skipping letters already shown), at most 10 letter guesses, stopping early when the board is
complete, then "I give up. What was the word? Reply with just the word." (W_final). Each turn is a
separate Claude Code invocation continuing the same session (`--resume`), exactly as in the coding
experiment, so the transcript is the model's only cross-turn memory in `bare`.

Planned sample: 3 conditions × 2 reveal × 12 games = 72 games (reduced only if the usage window
runs out, in which case the reduction is by whole game index, never by outcome).

## Measures per game (mechanical)

- **L**: word length declared by the initial board.
- **B_t**: the board parsed from each reply (a sequence of L cells, letters or underscores). A reply
  from which no board of length L can be parsed is `unparseable` and the game is scored `invalid`
  (reported, not dropped).
- **W_final**: the word given at the end; **W_mid**: the word given at the reveal (reveal games).
- **valid_word**: W_final is in `/usr/share/dict/words` (case-insensitive) and has length L.
- **board_consistent**: for every t, B_t equals the mask of W_final by the letters guessed so far
  (a letter guessed that is in W_final appears at exactly its positions; absent letters never appear).
- **mid_consistent** (reveal games): W_mid == W_final, and every board after the reveal equals the
  mask of W_mid.
- **externalised**: (tools conditions) a file containing W_final existed in the working directory
  before the first letter guess was answered (from the per-turn file snapshot); and
  **read_back**: the model read that file at least once after writing it (Read tool call or `cat`).
- **Game outcome**: `consistent` if valid_word ∧ board_consistent ∧ (¬reveal ∨ mid_consistent);
  otherwise `inconsistent` with the first failing check named.

## Hypotheses (stated in advance)

- HH1: `bare` shows some inconsistent games (replicating Baldelli et al. qualitatively). If `bare` is
  already at ceiling, the experiment cannot distinguish the conditions and says so.
- HH2: `tools-note` has fewer inconsistent games than `bare`; `tools` lies in between, depending on
  whether the model externalises uncued (rate reported).
- HH3: reveal games are at least as consistent as no-reveal games in every condition (once the
  word is in the transcript it is a carrier); if `bare` reveal games are *less* consistent than
  no-reveal games, transcript-based carrying is unreliable, which is closer to Williams's reading.

## Couplet (loose analogue; labelled as such)

Williams's couplet evidence concerns planning features inside a forward pass. The behavioural
analogue here is weaker: the model is asked to decide the end-word of the second line before
writing anything, then to write the first line only; in a second turn to write the second line; in
`reveal` trials it is asked between the two turns which end-word it planned (W_plan). In
`tools-note` it is told to write the planned end-word to `plan.txt` first. Measure:
**honoured** = the last word of line 2 equals W_plan (reveal trials) or the file content
(`tools-note`); for `bare` no-reveal trials there is nothing to check and they are not scored.
Planned sample: 3 conditions × 12 trials, reveal only for `bare`/`tools`; `tools-note` uses the file.
Conclusion drawn from this part is limited to: "when a plan is stated in the transcript or a file,
the later action honours it at rate X".

## Not measured

Whether any of this reflects an internal state. The `bare` condition is Claude Code with tools
disabled, not a raw API call; its system prompt is Claude Code's.

## Addendum (2026-09-18 02:25 UTC, before any game in these arms): two uncued consultation arms

Neither existing tool arm nudges the model to *consult* a record. Two arms are added, identical to
`tools` except for one sentence, neither naming files or writing:

| Condition | Added sentence |
|---|---|
| `tools-careful` | "Accuracy matters more than speed here: check that every reply is correct before you send it." |
| `tools-auditable` | "A referee may ask you at any point to justify any earlier reply against your own record of the game." |

Crossed with reveal ∈ {0, 1}, 12 games each (48 games). Scored as the other arms, plus a third
externalisation measure: **read_back_during_guess**, whether any read of the scratch directory
happened while answering a letter guess (not only at the reveal or final turn). Prediction under
the hypothesis: these arms externalise *and* consult, and have fewer inconsistent games than
`tools`; under the null, they behave like `tools`.

## Addendum 2 (2026-09-18 02:35 UTC, before any game in these arms): forewarned and ceiling arms

| Condition | Added to the uncued tools intro |
|---|---|
| `tools-forewarned` | A description of how chat models typically fail at this role (contradicting earlier letter answers, drifting to another word, changing the length) with **no** mention of files, notes or any remedy. Tests whether knowing the failure mode is enough for the model to build its own fix. |
| `tools-consult` | "write the secret word to `secret.txt` … and before every later reply read `secret.txt` and answer from what it says." The ceiling reference: the harness supplies the whole loop. |

Crossed with reveal ∈ {0, 1}, 12 games each (48 games). Same measures. Predictions: `tools-consult`
near 100% consistent with read-backs during guesses in every game; `tools-forewarned` is the
informative cell: if it externalises *and* consults without being told how, the system closes the
loop on its own initiative given only awareness of the risk; if it behaves like `tools`, awareness
is not enough.
