# Can agents commit?

Williams argues that it is hard to claim that LLMs have intent because they are not able to commit. Is the same true for AI agents?

Let's start with the test to see if an AI commits. Baldelli et al. asked an LLM to play hangman and demonstrated that it changed its secret word across steps. They forked the chat thread at each step and asked it what the word was, showing the model responded inconsistently, proving it had not committed to the secret word in the beginning. Interestingly, one of the designs they tested simply keeps the model's hidden reasoning from turn to turn, and in those conditions it showed commitment. 

AI coding agents now keep their hidden reasoning from turn to turn by default. Does this mean they can commit properly?

The answer is yes. Here we demonstrate that standard agents like Claude Code exhibit commitment by repeating Baldelli's hangman test using Claude Code's default settings (which include private working memory), and compare to when the private working memory is removed. The result is that agents commit to the secret word in all 194 forks across all 10 games, against only 47 of 177 with memory removed. The two arms are identical in every other way, so private working memory is what causes the commitment. Below is a visual summary of all the rollouts.
