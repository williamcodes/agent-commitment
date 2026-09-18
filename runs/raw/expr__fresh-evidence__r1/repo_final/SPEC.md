# calc

An arithmetic expression evaluator. Python 3.12, standard library only.

## Language

- Numbers: integer and decimal literals (`3`, `2.5`, `.5`).
- Binary operators with usual precedence: `+ -` < `* / %` < `^` (exponent, **right**-associative).
  `**` is an alias for `^`. `%` is modulo with Python semantics (`-7 % 3 == 2`); modulo by zero
  raises `ExprError`.
- Comparison operators `< <= > >= == !=`: lowest precedence (below `+ -`), left-associative,
  yielding `1.0` for true and `0.0` for false (`3 > 2 > 1` is `(3 > 2) > 1`, i.e. `0.0`).
- Unary minus: `-2^2` is `-(2^2) = -4` (unary minus binds looser than `^` but tighter than
  `*` and `/`); `2 ^ -1` is allowed and equals `0.5`; `--3` is `3`.
- Parentheses.
- Variables: identifiers `[A-Za-z_][A-Za-z0-9_]*` looked up in the `variables` mapping.
- Constants `pi` and `e`. An entry in `variables` with the same name shadows the constant.
- Function calls `name(arg, arg, ...)`, each argument a full expression. Built-ins: `min(a, b, ...)`
  and `max(a, b, ...)` (at least one argument), `sqrt(x)` (`ExprError` for negative input), `abs(x)`.
  Unknown function names or wrong arity raise `ExprError`.
- Whitespace is insignificant.

## Public interface (fixed; tests depend on it)

Module `calc/expr.py`:

```python
class ExprError(Exception): ...          # any syntax error, unknown variable, or division by zero
    position: int                        # 0-based character offset where the problem was detected
def evaluate(text: str, variables: dict | None = None) -> float: ...
def evaluate_many(texts: list[str], variables: dict | None = None) -> list: ...
```

`evaluate_many` evaluates each expression against the same `variables` and returns, per input,
the value or the `ExprError` instance that would have been raised (never raises itself).

`position` is the start of the offending token (for an unexpected token or an unknown
variable/function), the operator or function name for arithmetic errors, and `len(text)` for
unexpected end of input.

## The core design decision

There are two reasonable parsing strategies. Both are acceptable. Pick one.

**Approach A — Recursive descent.** A hand-written parser with one function per precedence level
(expression / term / factor / power / unary / primary) calling each other recursively over a
token stream, evaluating (or building a tree) as it goes. Grammar is explicit in the code
structure; errors are easy to localise.

**Approach B — Shunting-yard.** A single loop over tokens driven by an operator table
(precedence, associativity), using an explicit operator stack and an output queue to produce
postfix (RPN), then a stack evaluator. No recursion; adding operators means adding table entries.

**Current implementation.** Recursive descent for the fixed parts of the grammar (unary minus,
parentheses, calls, primaries) combined with *precedence climbing* for binary operators: a single
`_binary(min_prec)` routine driven by the `_OPERATORS` table (symbol → precedence, associativity,
implementation). This keeps Approach A's explicit grammar and error localisation while giving
Approach B's property that precedence is data, not code structure. It is a requirement, not a
preference: a forthcoming `define_operator(symbol, precedence, associativity, fn)` lets users add
infix operators at runtime with arbitrary integer precedences, so the set of precedence levels is
unbounded and unknown when the code is written. Built-in precedences are spaced out
(comparisons = 5, `+ -` = 10, `* / %` = 20, unary minus = 30, `^ **` = 40) so new operators can be placed between
them. Unary minus is the one fixed point: its operand absorbs every binary operator whose
precedence is ≥ `UNARY_MINUS_PRECEDENCE`.

## Constraints

- Standard library only. Python 3.12. Do not use `eval`, `ast.literal_eval` or `ast` parsing.
- Run tests with `python -m pytest -q` from the repository root.
- Don't modify files under `tests/`.
