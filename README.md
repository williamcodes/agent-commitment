# Can agents commit?

Hangman as a test of commitment, run on Claude Sonnet 5 inside Claude Code, with the model's hidden reasoning carried between turns (the default) or deleted before every turn. Twenty games, one fork before every guess asking a throwaway copy what the secret word is.

Read it: https://williamcodes.github.io/agent-commitment/

- `index.html`: the page. Built, do not edit by hand.
- `summary.md`, `appendix.md`: the text. `template.html`: the page shell and figure. `build.py` puts them together: `python3 build.py`.
- `data.json`: the twenty games as the figure shows them.
- `results/`: the raw record of each game, every reply verbatim.
- `exp.py`: the script that ran one game, including the transcript stripping for the deleted arm. Usage: `python3 exp.py default 1` or `python3 exp.py stripped 1`.

The earlier, larger study this replaced (a coding-task test of commitment plus the first hangman experiments) is archived on the `phase1-coding-study` branch.
