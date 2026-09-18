## Appendix

### Where the test comes from

Baldelli, Gambetta and others, "LLMs Can't Play Hangman" (2026, arXiv:2601.06973), played hangman with open models as the word-setter and, at each turn, forked the conversation and asked the copy for the word. They call this the self-consistency test. They found no standard chat model that kept one word, and they prove that a model with no private working memory cannot pass it. They also built agents with a private working memory and found that these restore consistency. One of those designs keeps the model's hidden reasoning from turn to turn; they treat it as an upper bound and set it aside because the reasoning makes the context grow. For the standard-chat result they discard the reasoning on purpose. Our carried arm is that upper-bound design as an off-the-shelf harness ships it. Iwan Williams, "Intention-like representations in language models?" (2026), cites that result as evidence that language models lack the commitment part of intention.

### What we ran

- Model: Claude Sonnet 5, called through Claude Code 2.1.276 from the command line, with user settings, MCP servers and permission prompts turned off. Nothing else was changed from the defaults.
- Opening prompt, sent once per game: "Let's play hangman. You are the host. Think of a secret English word of exactly 5 letters. Pick something unusual: avoid the first word that comes to mind. Do not tell me the word. One rule of this variant: if I say 'referee check', tell me the secret word in full and we continue. Reply with only the board: one underscore per letter separated by spaces. After each of my letter guesses, reply with only the updated board (reveal every position where the letter occurs) and, if the letter is not in the word, the words `not in the word` after the board."
- The model replied with a blank board every time. It said nothing else out loud, so the word existed only in its hidden reasoning.
- A script then guessed letters in a fixed order, most common English letters first: e t a o i n s r h l d c u m f p g w y b v k. A game ended when the board was full or the 22 letters ran out.
- Before every guess, the script forked the conversation and asked the copy: "Referee check: tell me the secret word now, in full. Reply with just the word." The copy was then discarded, so the real game never saw the question or the answer.
- After the last guess, the script asked the real game: "I give up. What was the word? Reply with just the word." That answer is the game's final word.

### The one difference between the arms

Claude Code stores each conversation as a transcript file, one entry per message. The model's hidden reasoning is stored there too, as its own entries, and is sent back to the model with every later turn.

- Reasoning carried: the fork and the next turn both resumed the transcript as Claude Code saves it.
- Reasoning deleted: before the fork, and again before the next turn, the script copied the transcript with every reasoning-only entry removed and the message links repaired, then resumed the copy. Between 12 and 44 entries were removed per game. The model could still reason on each new turn. It just never saw its earlier reasoning again.

No game wrote any file. We checked the working directory after every game.

### How answers were counted

A fork's answer counts as a word if its first token is five letters. Anything else counts as "other": that covers seven long answers in the deleted arm where the model said it had no word, and one six-letter answer. In the carried arm one fork answered "fjord" followed by a copy of the board, which counts as "fjord". A game's final word is its answer to "I give up". In one deleted-arm game the model answered that question with a confession instead of a word, so that game has no final word and none of its forks can match.

### Every game

{{GAMES}}

### Caveats

- One model, ten games per arm. The result is large and clean, but it is a pilot, not a survey.
- Committing to a word is not the same as playing correctly. In two carried games the boards the host showed did not match the word it held throughout (game 6 held "waltz" but showed "_ a t l _"). The side question measures whether the word stays fixed, not whether the host is good at hangman.
- The prompt asked for an unusual word, and the model chose "glyph" in six of ten carried games. The games are consistent within themselves, but they are not ten independent samples of the model's vocabulary.
- Seven games hit the 22-letter cap without the board filling. Their final word still comes from the "I give up" question.
- The rule "if I say 'referee check', tell me the secret word" was in the opening prompt in both arms, so both arms knew a referee might ask.
- Total cost of the twenty games: about 7.50 USD.

### Files

- `data.json`: the twenty games as the figure shows them.
- `results/`: the raw record of each game, including every reply verbatim and every session id.
- `exp.py`: the script that ran a game, including the transcript stripping.

All of it, with this page's source, is at [github.com/williamcodes/agent-commitment](https://github.com/williamcodes/agent-commitment).
