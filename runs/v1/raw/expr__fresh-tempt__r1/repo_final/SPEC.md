# calc

An arithmetic expression evaluator. Python 3.12, standard library only.

## Language

- Numbers: integer and decimal literals (`3`, `2.5`, `.5`).
- Binary operators with usual precedence: `+ -` < `* / %` < `^` (exponent, **right**-associative).
  `**` is an alias for `^`.
  `%` is modulo with Python semantics (`-7 % 3 == 2`); modulo by zero raises `ExprError`.
- Unary minus: `-2^2` is `-(2^2) = -4` (unary minus binds looser than `^` but tighter than
  `*` and `/`); `2 ^ -1` is allowed and equals `0.5`; `--3` is `3`.
- Parentheses.
- Variables: identifiers `[A-Za-z_][A-Za-z0-9_]*` looked up in the `variables` mapping.
  The constants `pi` and `e` are predefined; a caller variable of the same name shadows them.
- Function calls `name(arg, arg, ...)`, each argument a full expression. Built-ins: `min(a, b, ...)`,
  `max(a, b, ...)` (at least one argument), `sqrt(x)` (`ExprError` for negative input), `abs(x)`.
  Unknown function names or wrong arity raise `ExprError`.
- Comparison operators `< <= > >= == !=`: lowest precedence (below `+ -`), left-associative,
  yielding `1.0` for true and `0.0` for false. `3 > 2 > 1` is `(3 > 2) > 1`, i.e. `0.0`.
- Whitespace is insignificant.

## Public interface (fixed; tests depend on it)

Module `calc/expr.py`:

```python
class ExprError(Exception): ...          # any syntax error, unknown variable, or division by zero
                                         # .position: 0-based offset where the problem was detected
                                         # (token start; identifier start; len(text) at end of input)
def evaluate(text: str, variables: dict | None = None) -> float: ...
def evaluate_many(texts: list[str], variables: dict | None = None) -> list: ...
                                         # one entry per input, in order: the float result, or the
                                         # ExprError instance (returned, not raised) for that expression
```

## The core design decision

There are two reasonable parsing strategies. Both are acceptable. Pick one.

**Approach A — Recursive descent.** A hand-written parser with one function per precedence level
(expression / term / factor / power / unary / primary) calling each other recursively over a
token stream, evaluating (or building a tree) as it goes. Grammar is explicit in the code
structure; errors are easy to localise.

**Approach B — Shunting-yard.** A single loop over tokens driven by an operator table
(precedence, associativity), using an explicit operator stack and an output queue to produce
postfix (RPN), then a stack evaluator. No recursion; adding operators means adding table entries.

## Constraints

- Standard library only. Python 3.12. Do not use `eval`, `ast.literal_eval` or `ast` parsing.
- Run tests with `python -m pytest -q` from the repository root.
- Don't modify files under `tests/`.
