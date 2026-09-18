"""Arithmetic expression evaluator: recursive descent with precedence climbing.

Grammar::

    expression := unary (BINOP expression)*     # driven by _BINARY_OPERATORS
    unary      := '-' expression | primary       # operand parsed at _UNARY_MINUS_PRECEDENCE
    primary    := NUMBER | IDENT | call | '(' expression ')'
    call       := IDENT '(' (expression (',' expression)*)? ')'

Binary operators are *not* encoded in the function structure.  A single
``_Parser._expression(min_precedence)`` loop consults ``_BINARY_OPERATORS``
(symbol -> precedence, associativity, implementation) and recurses for the
right operand with the appropriate minimum precedence: the operator's own
precedence for right-associative operators, one higher for left-associative
ones.  Any number of distinct integer precedence levels therefore work
without touching the parser, and the tokenizer builds its operator pattern
from the same table (longest symbol first, so ``**`` beats ``*``).  Adding an
operator, including at runtime, means adding one table entry.

Unary minus is a fixed prefix operator whose operand is parsed with
``_UNARY_MINUS_PRECEDENCE``: looser than ``^`` (``-2^2 == -4``) but tighter
than ``*`` and ``/``.  ``2 ^ -1`` works because a right operand is parsed
through ``unary``.

``%`` is modulo with Python semantics (``-7 % 3 == 2``) at the same level as
``*`` and ``/``.  The comparisons ``< <= > >= == !=`` sit below ``+`` and
``-``, are left-associative, and yield ``1.0`` or ``0.0`` (so ``3 > 2 > 1``
is ``(3 > 2) > 1 == 0``).  An identifier followed by ``(`` calls a built-in function
from ``_FUNCTIONS``; a bare identifier is looked up in the caller's variables
and then in ``_CONSTANTS`` (so variables shadow ``pi`` and ``e``).

``evaluate_many`` evaluates a list of expressions against one variable
mapping and returns each value, or the ``ExprError`` instance in place of the
value for expressions that fail, so one bad expression does not abort the
batch.

Every ``ExprError`` carries ``position``, the 0-based offset where the problem
was detected: the offending token's start, the operator or function name for
arithmetic failures, or ``len(text)`` for unexpected end of input.
Implementations of operators and functions know nothing about positions;
they raise ``ValueError``/``ArithmeticError`` and the parser attaches the
position of the token being applied.
"""

from __future__ import annotations

import math
import operator
import re
from collections.abc import Callable, Mapping
from typing import NamedTuple

__all__ = ["ExprError", "evaluate", "evaluate_many"]


class ExprError(Exception):
    """Raised for any syntax error, unknown variable, or arithmetic failure.

    ``position`` is the 0-based character offset in the input at which the
    problem was detected (``len(text)`` for unexpected end of input).
    """

    def __init__(self, message: str, position: int) -> None:
        super().__init__(f"{message} (at position {position})")
        self.message = message
        self.position = position


class Token(NamedTuple):
    kind: str  # "num", "ident", "op", or "end"
    text: str
    pos: int


# -- operator and function tables -------------------------------------------


class _BinaryOperator(NamedTuple):
    precedence: int
    right_associative: bool
    apply: Callable[[float, float], float]


def _divide(a: float, b: float) -> float:
    if b == 0:
        raise ValueError("division by zero")
    return a / b


def _modulo(a: float, b: float) -> float:
    if b == 0:
        raise ValueError("modulo by zero")
    return a % b


def _power(base: float, exponent: float) -> float:
    try:
        result = base**exponent
    except ZeroDivisionError:
        raise ValueError("zero raised to a negative power") from None
    except OverflowError:
        raise ValueError("result too large") from None
    if isinstance(result, complex):
        raise ValueError("result is not a real number")
    return result


def _sqrt(x: float) -> float:
    if x < 0:
        raise ValueError("sqrt of a negative number")
    return math.sqrt(x)


# Precedences are spaced out so further levels can be slotted between them.
# Comparisons are the loosest level; ``_apply`` turns their bool into 1.0/0.0.
_BINARY_OPERATORS: dict[str, _BinaryOperator] = {
    "<": _BinaryOperator(0, False, operator.lt),
    "<=": _BinaryOperator(0, False, operator.le),
    ">": _BinaryOperator(0, False, operator.gt),
    ">=": _BinaryOperator(0, False, operator.ge),
    "==": _BinaryOperator(0, False, operator.eq),
    "!=": _BinaryOperator(0, False, operator.ne),
    "+": _BinaryOperator(10, False, operator.add),
    "-": _BinaryOperator(10, False, operator.sub),
    "*": _BinaryOperator(20, False, operator.mul),
    "/": _BinaryOperator(20, False, _divide),
    "%": _BinaryOperator(20, False, _modulo),
    "^": _BinaryOperator(30, True, _power),
    "**": _BinaryOperator(30, True, _power),
}

# Looser than "^" and "**", tighter than "*", "/" and "%".  Comparisons and
# "+"/"-" are looser still, so "-1 < 2" parses as "(-1) < 2".
_UNARY_MINUS_PRECEDENCE = 25

# name -> (min arity, max arity or None for unbounded, implementation)
_FUNCTIONS: dict[str, tuple[int, int | None, Callable[..., float]]] = {
    "min": (1, None, min),
    "max": (1, None, max),
    "sqrt": (1, 1, _sqrt),
    "abs": (1, 1, abs),
}

_CONSTANTS: dict[str, float] = {"pi": math.pi, "e": math.e}

_PUNCTUATION = ("(", ")", ",")


# -- tokenizer ----------------------------------------------------------------


def _token_re() -> re.Pattern[str]:
    """Build the token pattern from the current operator table.

    Symbols are tried longest first so multi-character operators such as
    ``**`` win over their prefixes.  ``re.compile`` caches, so this is cheap.
    """
    symbols = sorted(set(_BINARY_OPERATORS) | set(_PUNCTUATION), key=len, reverse=True)
    ops = "|".join(map(re.escape, symbols))
    return re.compile(
        rf"(?P<ws>\s+)|(?P<num>\d+(?:\.\d*)?|\.\d+)|(?P<ident>[A-Za-z_][A-Za-z0-9_]*)|(?P<op>{ops})"
    )


def _tokenize(text: str) -> list[Token]:
    pattern = _token_re()
    tokens: list[Token] = []
    pos = 0
    while pos < len(text):
        match = pattern.match(text, pos)
        if match is None:
            raise ExprError(f"unexpected character {text[pos]!r}", pos)
        kind = match.lastgroup
        if kind != "ws":
            tokens.append(Token(kind, match.group(), pos))
        pos = match.end()
    tokens.append(Token("end", "", len(text)))
    return tokens


# -- parser -------------------------------------------------------------------


class _Parser:
    def __init__(self, text: str, variables: Mapping[str, float]) -> None:
        self._tokens = _tokenize(text)
        self._index = 0
        self._variables = variables

    # -- token helpers -----------------------------------------------------

    def _peek(self) -> Token:
        return self._tokens[self._index]

    def _advance(self) -> Token:
        token = self._tokens[self._index]
        self._index += 1
        return token

    def _at_op(self, *symbols: str) -> bool:
        token = self._peek()
        return token.kind == "op" and token.text in symbols

    def _expect_op(self, symbol: str) -> None:
        if not self._at_op(symbol):
            raise self._error(f"expected {symbol!r}")
        self._advance()

    def _error(self, message: str) -> ExprError:
        """An error at the current token (``len(text)`` at end of input)."""
        token = self._peek()
        if token.kind == "end":
            return ExprError(f"{message} but reached end of input", token.pos)
        return ExprError(f"{message} but found {token.text!r}", token.pos)

    @staticmethod
    def _apply(fn: Callable[..., float], args: tuple[float, ...], pos: int) -> float:
        """Call an operator or function implementation, localising failures to ``pos``."""
        try:
            return float(fn(*args))
        except (ArithmeticError, ValueError) as exc:
            raise ExprError(str(exc), pos) from None

    # -- grammar -----------------------------------------------------------

    def parse(self) -> float:
        value = self._expression()
        if self._peek().kind != "end":
            raise self._error("expected end of input")
        return value

    def _expression(self, min_precedence: int | None = None) -> float:
        """Precedence climbing: parse binary operators of at least ``min_precedence``."""
        value = self._unary()
        while True:
            token = self._peek()
            op = _BINARY_OPERATORS.get(token.text) if token.kind == "op" else None
            if op is None or (min_precedence is not None and op.precedence < min_precedence):
                return value
            self._advance()
            rhs_min = op.precedence if op.right_associative else op.precedence + 1
            rhs = self._expression(rhs_min)
            value = self._apply(op.apply, (value, rhs), token.pos)

    def _unary(self) -> float:
        if self._at_op("-"):
            self._advance()
            return -self._expression(_UNARY_MINUS_PRECEDENCE)
        return self._primary()

    def _primary(self) -> float:
        token = self._peek()
        if token.kind == "num":
            self._advance()
            return float(token.text)
        if token.kind == "ident":
            self._advance()
            if self._at_op("("):
                return self._call(token)
            return self._lookup(token)
        if self._at_op("("):
            self._advance()
            value = self._expression()
            self._expect_op(")")
            return value
        raise self._error("expected a number, variable, or '('")

    def _lookup(self, token: Token) -> float:
        name = token.text
        if name in self._variables:
            try:
                return float(self._variables[name])
            except (TypeError, ValueError):
                raise ExprError(f"variable {name!r} is not numeric", token.pos) from None
        if name in _CONSTANTS:
            return _CONSTANTS[name]
        raise ExprError(f"unknown variable {name!r}", token.pos)

    def _call(self, name_token: Token) -> float:
        name = name_token.text
        if name not in _FUNCTIONS:
            raise ExprError(f"unknown function {name!r}", name_token.pos)
        lo, hi, func = _FUNCTIONS[name]
        self._expect_op("(")
        args: list[float] = []
        if not self._at_op(")"):
            args.append(self._expression())
            while self._at_op(","):
                self._advance()
                args.append(self._expression())
        self._expect_op(")")
        n = len(args)
        if n < lo or (hi is not None and n > hi):
            if hi is None:
                want = f"at least {lo}"
            elif lo == hi:
                want = f"exactly {lo}"
            else:
                want = f"between {lo} and {hi}"
            raise ExprError(f"{name}() takes {want} argument(s) but {n} were given", name_token.pos)
        return self._apply(func, tuple(args), name_token.pos)


def evaluate(text: str, variables: Mapping[str, float] | None = None) -> float:
    """Evaluate an arithmetic expression and return the result as a float.

    Raises ExprError (with ``.position``) for syntax errors, unknown variables
    or functions, wrong argument counts, sqrt of a negative number, and
    division or modulo by zero.
    """
    return _Parser(text, {} if variables is None else variables).parse()


def evaluate_many(
    texts: list[str], variables: Mapping[str, float] | None = None
) -> list[float | ExprError]:
    """Evaluate each expression in ``texts`` against the same ``variables``.

    Returns one entry per input, in order: the float result, or the
    ``ExprError`` that the expression raised.  Errors are returned rather
    than raised so that one bad expression does not abort the batch.
    """
    results: list[float | ExprError] = []
    for text in texts:
        try:
            results.append(evaluate(text, variables))
        except ExprError as exc:
            results.append(exc)
    return results
