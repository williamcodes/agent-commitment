"""Arithmetic expression evaluator (table-driven precedence-climbing parser).

Binary operators are described by a table (``_BINARY_OPS``) of precedence,
associativity and implementation, and a single ``_expr(min_precedence)``
routine consumes any operator whose precedence is at least ``min_precedence``.
Precedence levels are therefore plain integers, not functions: adding an
operator (including at a new, previously unknown level) is one table entry,
and no parsing code changes.  This is what makes a future
``define_operator(symbol, precedence, associativity, fn)`` a trivial addition.

Built-in table, lowest precedence first::

     0   < <= > >= == !=   left    (yield 1.0 for true, 0.0 for false)
    10   + -            left
    20   * / %          left
    30   (unary minus)  binds its operand at this level
    40   ^  **          right   (** is an alias of ^)

Unary minus binds its operand with minimum precedence ``_UNARY_MINUS_PRECEDENCE``:
tighter than ``*`` and ``/`` (``2 * -3 == -6``, ``-2 * 3 == -6``) but looser
than ``^`` (``-2^2 == -4``).  ``2 ^ -1`` works because the right operand of
any operator is parsed as a full prefix expression.  ``%`` follows Python
semantics (``-7 % 3 == 2``).  Comparisons are ordinary left-associative
binary operators at the lowest level, so ``3 > 2 > 1`` is ``(3 > 2) > 1``,
i.e. ``1 > 1 == 0`` (no Python-style chaining).

Primaries: numbers, identifiers (variables passed by the caller, falling back
to the constants ``pi`` and ``e``), calls ``name(args)`` to the built-in
functions ``min``/``max`` (one or more arguments) and ``sqrt``/``abs``
(exactly one), and parenthesised expressions.

Every ``ExprError`` carries ``.position``, the 0-based character offset where
the problem was detected: the offending token's start, or ``len(text)`` for
unexpected end of input.

``evaluate_many(texts, variables)`` evaluates several expressions against the
same variables and returns a list containing, for each input, either its
value or the ``ExprError`` it raised (nothing is raised).
"""

from __future__ import annotations

import math
import operator
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Literal, NamedTuple


class ExprError(Exception):
    """Raised for syntax errors, unknown variables/functions, bad arity,
    division or modulo by zero, or invalid operands.

    ``position`` is the 0-based character offset in the input at which the
    problem was detected; ``message`` is the description without it.
    """

    def __init__(self, message: str, position: int) -> None:
        super().__init__(f"{message} (at position {position})")
        self.message = message
        self.position = position


# --------------------------------------------------------------------------
# Operator and function tables
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class _BinaryOp:
    precedence: int
    associativity: Literal["left", "right"]
    fn: Callable[[float, float], float]

    def rhs_min_precedence(self) -> int:
        """Minimum precedence an operator needs to be absorbed into our right
        operand: strictly higher for left-associative, equal or higher for
        right-associative (so ``2 ^ 3 ^ 2 == 2 ^ (3 ^ 2)``)."""
        return self.precedence if self.associativity == "right" else self.precedence + 1


def _power(base: float, exponent: float) -> float:
    result = base**exponent  # may raise OverflowError or ZeroDivisionError
    if isinstance(result, complex):
        raise ValueError("no real result")
    return result


_POWER = _BinaryOp(40, "right", _power)

_BINARY_OPS: dict[str, _BinaryOp] = {
    # Comparisons: lowest precedence, left-associative.  The implementations
    # return bool, which ``_apply`` converts to 1.0 / 0.0.
    "<": _BinaryOp(0, "left", operator.lt),
    "<=": _BinaryOp(0, "left", operator.le),
    ">": _BinaryOp(0, "left", operator.gt),
    ">=": _BinaryOp(0, "left", operator.ge),
    "==": _BinaryOp(0, "left", operator.eq),
    "!=": _BinaryOp(0, "left", operator.ne),
    "+": _BinaryOp(10, "left", operator.add),
    "-": _BinaryOp(10, "left", operator.sub),
    "*": _BinaryOp(20, "left", operator.mul),
    "/": _BinaryOp(20, "left", operator.truediv),
    "%": _BinaryOp(20, "left", operator.mod),
    "^": _POWER,
    "**": _POWER,
}

# Unary minus absorbs every binary operator with at least this precedence
# into its operand.  Sits between "* /" (20) and "^" (40).
_UNARY_MINUS_PRECEDENCE = 30

# Minimum precedence for a top-level expression: absorb everything.
_LOWEST_PRECEDENCE = -math.inf

# Non-operator punctuation the tokenizer must also recognise.
_PUNCTUATION = ("(", ")", ",")


def _sqrt(x: float) -> float:
    if x < 0:
        raise ValueError(f"sqrt of negative number {x}")
    return math.sqrt(x)


# name -> (implementation, minimum arity, maximum arity or None for unbounded)
_FUNCTIONS: dict[str, tuple[Callable[..., float], int, int | None]] = {
    "min": (min, 1, None),
    "max": (max, 1, None),
    "sqrt": (_sqrt, 1, 1),
    "abs": (abs, 1, 1),
}

# Looked up only when the caller's ``variables`` has no entry for the name.
_CONSTANTS: dict[str, float] = {
    "pi": math.pi,
    "e": math.e,
}


# --------------------------------------------------------------------------
# Tokenizer
# --------------------------------------------------------------------------


class _Token(NamedTuple):
    kind: str  # "num" | "ident" | "op" | "end"
    value: str
    position: int


def _token_re() -> re.Pattern[str]:
    """Build the token regex from the operator table so that operator symbols
    are always tokenized greedily (``**`` before ``*``) and a new table entry
    is automatically recognised.  ``re.compile`` caches the result."""
    symbols = sorted(set(_BINARY_OPS) | set(_PUNCTUATION), key=len, reverse=True)
    ops = "|".join(re.escape(s) for s in symbols)
    return re.compile(
        rf"""
        \s*(?:
            (?P<num>\d+\.\d*|\.\d+|\d+)
          | (?P<ident>[A-Za-z_][A-Za-z0-9_]*)
          | (?P<op>{ops})
          | (?P<bad>\S)
        )
        """,
        re.VERBOSE,
    )


def _tokenize(text: str) -> list[_Token]:
    tokens: list[_Token] = []
    for m in _token_re().finditer(text):
        kind = m.lastgroup
        if kind is None:  # trailing whitespace only
            continue
        value = m.group(kind)
        position = m.start(kind)
        if kind == "bad":
            raise ExprError(f"unexpected character {value!r}", position)
        tokens.append(_Token(kind, value, position))
    tokens.append(_Token("end", "", len(text)))
    return tokens


# --------------------------------------------------------------------------
# Parser / evaluator
# --------------------------------------------------------------------------


class _Parser:
    def __init__(self, tokens: list[_Token], variables: Mapping[str, float]):
        self._tokens = tokens
        self._pos = 0
        self._variables = variables

    # -- token helpers -------------------------------------------------

    def _peek(self) -> _Token:
        return self._tokens[self._pos]

    def _advance(self) -> _Token:
        tok = self._tokens[self._pos]
        self._pos += 1
        return tok

    def _accept_op(self, *ops: str) -> _Token | None:
        tok = self._peek()
        if tok.kind == "op" and tok.value in ops:
            return self._advance()
        return None

    def _expect_op(self, op: str) -> None:
        if self._accept_op(op) is None:
            tok = self._peek()
            raise ExprError(f"expected {op!r}, found {_describe(tok)}", tok.position)

    # -- grammar -------------------------------------------------------

    def parse(self) -> float:
        value = self._expr(_LOWEST_PRECEDENCE)
        tok = self._peek()
        if tok.kind != "end":
            raise ExprError(f"unexpected token {tok.value!r}", tok.position)
        return value

    def _expr(self, min_precedence: float) -> float:
        """Precedence climbing: parse a prefix expression, then keep absorbing
        binary operators whose precedence is at least ``min_precedence``."""
        lhs = self._prefix()
        while True:
            tok = self._peek()
            op = _BINARY_OPS.get(tok.value) if tok.kind == "op" else None
            if op is None or op.precedence < min_precedence:
                return lhs
            self._advance()
            rhs = self._expr(op.rhs_min_precedence())
            lhs = _apply(op.fn, (lhs, rhs), f"cannot compute {lhs} {tok.value} {rhs}", tok.position)

    def _prefix(self) -> float:
        if self._accept_op("-") is not None:
            return -self._expr(_UNARY_MINUS_PRECEDENCE)
        return self._primary()

    def _primary(self) -> float:
        tok = self._advance()
        if tok.kind == "num":
            return float(tok.value)
        if tok.kind == "ident":
            if self._accept_op("(") is not None:
                return self._call(tok)
            return self._lookup(tok)
        if tok.kind == "op" and tok.value == "(":
            inner = self._expr(_LOWEST_PRECEDENCE)
            self._expect_op(")")
            return inner
        raise ExprError(
            f"expected a number, variable or '(', found {_describe(tok)}", tok.position
        )

    def _lookup(self, tok: _Token) -> float:
        name = tok.value
        if name in self._variables:
            return float(self._variables[name])
        if name in _CONSTANTS:
            return _CONSTANTS[name]
        raise ExprError(f"unknown variable {name!r}", tok.position)

    def _call(self, name_tok: _Token) -> float:
        """Parse the argument list of ``name(`` (the "(" is already consumed)."""
        name = name_tok.value
        args: list[float] = []
        if self._accept_op(")") is None:
            args.append(self._expr(_LOWEST_PRECEDENCE))
            while self._accept_op(",") is not None:
                args.append(self._expr(_LOWEST_PRECEDENCE))
            self._expect_op(")")
        if name not in _FUNCTIONS:
            raise ExprError(f"unknown function {name!r}", name_tok.position)
        func, min_args, max_args = _FUNCTIONS[name]
        if len(args) < min_args or (max_args is not None and len(args) > max_args):
            if max_args is None:
                expected = f"at least {min_args}"
            elif min_args == max_args:
                expected = str(min_args)
            else:
                expected = f"between {min_args} and {max_args}"
            raise ExprError(
                f"{name}() takes {expected} argument(s), got {len(args)}", name_tok.position
            )
        return _apply(func, args, f"{name}()", name_tok.position)


def _describe(tok: _Token) -> str:
    return "end of input" if tok.kind == "end" else repr(tok.value)


def _apply(fn: Callable[..., float], args, what: str, position: int) -> float:
    """Call an operator/function implementation, converting arithmetic
    failures into a positioned ``ExprError``."""
    try:
        return float(fn(*args))
    except (ZeroDivisionError, OverflowError, ValueError) as exc:
        raise ExprError(f"{what}: {exc}", position) from exc


def evaluate(text: str, variables: Mapping[str, float] | None = None) -> float:
    """Evaluate an arithmetic expression and return the result as a float."""
    tokens = _tokenize(text)
    return _Parser(tokens, variables or {}).parse()


def evaluate_many(
    texts: list[str], variables: Mapping[str, float] | None = None
) -> list[float | ExprError]:
    """Evaluate each expression in ``texts`` against the same ``variables``.

    Returns a list, parallel to ``texts``, holding each expression's value or,
    if it failed, the ``ExprError`` instance itself.  Never raises
    ``ExprError``; one bad expression does not prevent the others from being
    evaluated.
    """
    results: list[float | ExprError] = []
    for text in texts:
        try:
            results.append(evaluate(text, variables))
        except ExprError as exc:
            results.append(exc)
    return results
