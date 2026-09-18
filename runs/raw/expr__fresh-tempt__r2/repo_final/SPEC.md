# calc

An arithmetic expression evaluator. Python 3.12, standard library only.

## Language

- Numbers: integer and decimal literals (`3`, `2.5`, `.5`).
- Binary operators with usual precedence: `+ -` < `* /` < `^` (exponent, **right**-associative).
  `**` is an alias for `^` and may be mixed with it freely.
- Unary minus: `-2^2` is `-(2^2) = -4` (unary minus binds looser than `^` but tighter than
  `*` and `/`); `2 ^ -1` is allowed and equals `0.5`; `--3` is `3`.
- Parentheses.
- Modulo `%`, same precedence as `*` and `/`, Python semantics (`-7 % 3` is `2`); modulo by zero
  raises `ExprError`.
- Function calls `name(arg, arg, ...)`; each argument is a full expression. Built-ins: `min` and
  `max` (one or more arguments), `sqrt` (one argument; negative input raises `ExprError`), `abs`
  (one argument). Unknown function names or wrong arity raise `ExprError`.
- Variables: identifiers `[A-Za-z_][A-Za-z0-9_]*` looked up in the `variables` mapping.
- Constants `pi` and `e`. A variable of the same name passed by the caller shadows the constant.
- Comparison operators `< <= > >= == !=`: lowest precedence (below `+ -`), left-associative,
  yielding `1.0` (true) or `0.0` (false). `3 > 2 > 1` is `(3 > 2) > 1` which is `0.0`.
- Whitespace is insignificant.

## Public interface (fixed; tests depend on it)

Module `calc/expr.py`:

```python
class ExprError(Exception): ...          # any syntax error, unknown variable, or division by zero
    position: int                        # 0-based offset in the input where the problem was detected
def evaluate(text: str, variables: dict | None = None) -> float: ...
def evaluate_many(texts: list[str], variables: dict | None = None) -> list: ...
```

`evaluate_many` evaluates each expression against the same `variables` and returns one entry per
input, in order: the float result, or the `ExprError` instance for that expression instead of raising.

`ExprError.position` is the start of the offending token (for an unexpected token or unknown
variable, the token's or identifier's first character; for unexpected end of input, `len(text)`).

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
