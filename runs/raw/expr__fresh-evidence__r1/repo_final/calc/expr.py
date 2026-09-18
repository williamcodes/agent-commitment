"""Arithmetic expression evaluator: recursive descent with precedence climbing.

Grammar::

    expression := binary
    binary     := unary (BINOP binary)*        # driven by the _OPERATORS table
    unary      := '-' binary | primary         # operand absorbs ops binding >= UNARY_MINUS_PRECEDENCE
    primary    := NUMBER | call | IDENT | '(' expression ')'
    call       := IDENT '(' (expression (',' expression)*)? ')'

Binary operators are *not* baked into the function structure. A single
``_binary(min_prec)`` routine consults the ``_OPERATORS`` table (symbol ->
precedence, associativity, implementation), so the number of precedence levels
is unbounded and operators can be added at runtime by inserting table entries.
Unary minus is the one fixed point: its operand extends over every binary
operator whose precedence is at least ``UNARY_MINUS_PRECEDENCE``, which makes
``-2^2`` parse as ``-(2^2)`` while ``2 * -3`` and ``2 ^ -1`` still work.

Comparison operators (``< <= > >= == !=``) are ordinary table entries at the
lowest precedence, left-associative, yielding ``1.0`` or ``0.0``; the grammar
does not need a dedicated level for them.

Every ``ExprError`` carries ``.position``, the 0-based character offset where
the problem was detected.
"""

from __future__ import annotations

import math
import operator
import re
from collections.abc import Callable, Mapping
from typing import NamedTuple


class ExprError(Exception):
    """Raised for any syntax error, unknown variable, or arithmetic error.

    ``position`` is the 0-based character offset in the input where the
    problem was detected: the start of an unexpected token or identifier,
    the operator/function for arithmetic errors, or ``len(text)`` for
    unexpected end of input.
    """

    def __init__(self, message: str, position: int):
        super().__init__(f"{message} (at position {position})")
        self.message = message
        self.position = position


# --- operator table --------------------------------------------------------

LEFT = "left"
RIGHT = "right"


class Operator(NamedTuple):
    precedence: int
    associativity: str  # LEFT or RIGHT
    fn: Callable[[float, float], float]


def _pow(base: float, exponent: float) -> float:
    result = base**exponent  # may raise ZeroDivisionError / OverflowError
    if isinstance(result, complex):
        raise ValueError("fractional power of a negative number")
    return float(result)


def _comparison(cmp: Callable[[float, float], bool]) -> Callable[[float, float], float]:
    """Wrap a boolean comparison so that it yields ``1.0`` (true) or ``0.0`` (false)."""
    return lambda a, b: 1.0 if cmp(a, b) else 0.0


# Precedences are spread out so that operators defined later can slot between
# the built-in levels. Higher binds tighter. Unary minus sits between the
# multiplicative and exponent levels (see UNARY_MINUS_PRECEDENCE).
_OPERATORS: dict[str, Operator] = {
    # Comparisons bind loosest and are left-associative: 3 > 2 > 1 == (3 > 2) > 1 == 0.
    "<": Operator(5, LEFT, _comparison(operator.lt)),
    "<=": Operator(5, LEFT, _comparison(operator.le)),
    ">": Operator(5, LEFT, _comparison(operator.gt)),
    ">=": Operator(5, LEFT, _comparison(operator.ge)),
    "==": Operator(5, LEFT, _comparison(operator.eq)),
    "!=": Operator(5, LEFT, _comparison(operator.ne)),
    "+": Operator(10, LEFT, operator.add),
    "-": Operator(10, LEFT, operator.sub),
    "*": Operator(20, LEFT, operator.mul),
    "/": Operator(20, LEFT, operator.truediv),  # raises ZeroDivisionError
    "%": Operator(20, LEFT, operator.mod),  # Python semantics: -7 % 3 == 2
    "^": Operator(40, RIGHT, _pow),
}
_OPERATORS["**"] = _OPERATORS["^"]

#: Binary operators with precedence >= this are absorbed into the operand of a
#: unary minus (``-2^2 == -(2^2)``); those below it apply to the negated value
#: (``-2*3 == (-2)*3``, which is numerically the same but matters for errors).
UNARY_MINUS_PRECEDENCE = 30

_CONSTANTS: Mapping[str, float] = {"pi": math.pi, "e": math.e}


def _sqrt(x: float) -> float:
    if x < 0:
        raise ValueError(f"square root of negative number {x!r}")
    return math.sqrt(x)


# name -> (implementation taking the argument list, minimum arity, maximum arity or None)
_FUNCTIONS: dict[str, tuple[Callable[[list[float]], float], int, int | None]] = {
    "min": (min, 1, None),
    "max": (max, 1, None),
    "sqrt": (lambda args: _sqrt(args[0]), 1, 1),
    "abs": (lambda args: abs(args[0]), 1, 1),
}


# --- tokenizer ---------------------------------------------------------------


class Token(NamedTuple):
    kind: str  # "num", "ident", "op", "eof"
    text: str
    pos: int  # 0-based character offset of the token's first character


def _build_token_re() -> re.Pattern[str]:
    # Longest symbols first so that e.g. "**" is not tokenized as "*", "*".
    symbols = sorted(list(_OPERATORS) + ["(", ")", ","], key=len, reverse=True)
    ops = "|".join(re.escape(s) for s in symbols)
    return re.compile(
        rf"(?P<ws>\s+)|(?P<num>\d+\.\d*|\.\d+|\d+)|(?P<ident>[A-Za-z_][A-Za-z0-9_]*)|(?P<op>{ops})"
    )


_TOKEN_RE = _build_token_re()


def _tokenize(text: str) -> list[Token]:
    """Split ``text`` into tokens, ending with an ``eof`` sentinel at ``len(text)``."""
    tokens: list[Token] = []
    pos = 0
    while pos < len(text):
        m = _TOKEN_RE.match(text, pos)
        if m is None:
            raise ExprError(f"unexpected character {text[pos]!r}", pos)
        kind = m.lastgroup
        assert kind is not None
        if kind != "ws":
            tokens.append(Token(kind, m.group(), pos))
        pos = m.end()
    tokens.append(Token("eof", "", len(text)))
    return tokens


# --- parser / evaluator ------------------------------------------------------

_NO_BOUND = float("-inf")


class _Parser:
    def __init__(self, tokens: list[Token], variables: Mapping[str, float]):
        self._tokens = tokens
        self._i = 0
        self._variables = variables

    # -- token helpers -----------------------------------------------------

    def _peek(self) -> Token:
        return self._tokens[self._i]

    def _advance(self) -> Token:
        tok = self._tokens[self._i]
        self._i += 1
        return tok

    def _accept_op(self, *ops: str) -> Token | None:
        tok = self._peek()
        if tok.kind == "op" and tok.text in ops:
            return self._advance()
        return None

    def _expect_op(self, op: str) -> None:
        if self._accept_op(op) is None:
            tok = self._peek()
            raise ExprError(f"expected {op!r}, found {_describe(tok)}", tok.pos)

    # -- grammar -----------------------------------------------------------

    def parse(self) -> float:
        value = self._expression()
        tok = self._peek()
        if tok.kind != "eof":
            raise ExprError(f"unexpected token {tok.text!r}", tok.pos)
        return value

    def _expression(self) -> float:
        return self._binary(_NO_BOUND)

    def _binary(self, min_prec: float) -> float:
        """Parse ``unary (BINOP binary)*`` for operators binding at least as tightly as ``min_prec``."""
        lhs = self._unary()
        while True:
            tok = self._peek()
            op = _OPERATORS.get(tok.text) if tok.kind == "op" else None
            if op is None or op.precedence < min_prec:
                return lhs
            self._advance()
            # Left-assoc: the right operand may only contain tighter operators.
            # Right-assoc: it may also contain operators of the same precedence.
            rhs = self._binary(op.precedence + 1 if op.associativity == LEFT else op.precedence)
            lhs = _apply(op.fn, lhs, rhs, tok)

    def _unary(self) -> float:
        if self._accept_op("-") is not None:
            return -self._binary(UNARY_MINUS_PRECEDENCE)
        return self._primary()

    def _primary(self) -> float:
        tok = self._advance()
        if tok.kind == "num":
            return float(tok.text)
        if tok.kind == "ident":
            if self._accept_op("(") is not None:
                return self._call(tok)
            return self._lookup(tok)
        if tok.kind == "op" and tok.text == "(":
            value = self._expression()
            self._expect_op(")")
            return value
        raise ExprError(f"expected a number, variable or '(', found {_describe(tok)}", tok.pos)

    def _lookup(self, tok: Token) -> float:
        for scope in (self._variables, _CONSTANTS):  # caller's variables shadow constants
            if tok.text in scope:
                return float(scope[tok.text])
        raise ExprError(f"unknown variable {tok.text!r}", tok.pos)

    def _call(self, name: Token) -> float:
        """Parse the argument list of ``name(`` (the '(' is already consumed) and apply it."""
        try:
            func, min_args, max_args = _FUNCTIONS[name.text]
        except KeyError:
            raise ExprError(f"unknown function {name.text!r}", name.pos) from None
        args: list[float] = []
        if self._accept_op(")") is None:
            args.append(self._expression())
            while self._accept_op(",") is not None:
                args.append(self._expression())
            self._expect_op(")")
        if len(args) < min_args or (max_args is not None and len(args) > max_args):
            raise ExprError(
                f"{name.text}() takes {_arity_text(min_args, max_args)}, got {len(args)}", name.pos
            )
        try:
            return float(func(args))
        except (ArithmeticError, ValueError) as err:
            raise ExprError(f"{name.text}(): {err}", name.pos) from None


def _apply(fn: Callable[[float, float], float], lhs: float, rhs: float, tok: Token) -> float:
    try:
        return float(fn(lhs, rhs))
    except ZeroDivisionError:
        raise ExprError(f"division by zero in {tok.text!r}", tok.pos) from None
    except OverflowError:
        raise ExprError(f"result of {tok.text!r} too large", tok.pos) from None
    except ValueError as err:
        raise ExprError(f"{tok.text!r}: {err}", tok.pos) from None


def _describe(tok: Token) -> str:
    return "end of input" if tok.kind == "eof" else repr(tok.text)


def _arity_text(min_args: int, max_args: int | None) -> str:
    if max_args is None:
        return f"at least {min_args} argument(s)"
    if min_args == max_args:
        return f"exactly {min_args} argument(s)"
    return f"{min_args} to {max_args} arguments"


def evaluate(text: str, variables: Mapping[str, float] | None = None) -> float:
    """Evaluate the arithmetic expression ``text`` and return its value as a float.

    ``variables`` maps identifier names to numeric values and shadows the
    built-in constants ``pi`` and ``e``. Any syntax error, unknown variable, or
    arithmetic error (division/modulo by zero, ``sqrt`` of a negative number,
    ...) raises :class:`ExprError`, whose ``position`` attribute gives the
    0-based character offset where the problem was detected.
    """
    tokens = _tokenize(text)
    return _Parser(tokens, variables or {}).parse()


def evaluate_many(
    texts: list[str], variables: Mapping[str, float] | None = None
) -> list[float | ExprError]:
    """Evaluate each expression in ``texts`` against the same ``variables``.

    Returns one entry per input, in order: the value as a float, or, if that
    expression failed, the :class:`ExprError` instance itself in place of the
    value. Nothing is raised, so one bad expression does not hide the results
    of the others.
    """
    results: list[float | ExprError] = []
    for text in texts:
        try:
            results.append(evaluate(text, variables))
        except ExprError as err:
            results.append(err)
    return results
