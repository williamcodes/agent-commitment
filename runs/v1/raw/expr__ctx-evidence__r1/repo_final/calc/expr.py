"""Arithmetic expression evaluator.

Parsing strategy: precedence climbing (a Pratt-style parser). One recursive
function, ``_expr(min_prec)``, parses an operand and then loops over binary
operators, consulting an operator *table* for precedence and associativity.
Precedence levels are therefore data, not code structure: a new infix operator
at any integer precedence is a single table entry.

    expr(p)  := prefix { BINOP[prec >= p] expr(prec or prec+1) }
    prefix   := '-' expr(UNARY_MINUS_PREC) | primary
    primary  := NUMBER | call | IDENT | '(' expr(0) ')'
    call     := IDENT '(' [ expr(0) { ',' expr(0) } ] ')'

Unary minus parses its operand at ``_UNARY_MINUS_PREC``, which sits strictly
between ``* / %`` and ``^``. That yields ``-2^2 == -(2^2)`` while still allowing
``2 ^ -1`` (the right operand of ``^`` is parsed as a fresh prefix expression).

Every ``ExprError`` carries ``.position``: the 0-based character offset where
the problem was detected.
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass


class ExprError(Exception):
    """Syntax error, unknown name, bad arity, or invalid arithmetic (e.g. division by zero).

    ``position`` is the 0-based character offset in the input where the problem
    was detected (``len(text)`` for unexpected end of input).
    """

    def __init__(self, message: str, position: int):
        super().__init__(f"{message} (at position {position})")
        self.message = message
        self.position = position


# --------------------------------------------------------------------------
# Operator table
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class _BinaryOp:
    precedence: int
    associativity: str  # "left" | "right"
    fn: Callable[[float, float], float]


def _power(a: float, b: float) -> float:
    result = a**b  # may raise ZeroDivisionError / OverflowError; wrapped by caller
    if isinstance(result, complex):
        raise ValueError("result is not a real number")
    return result


# Precedences are sparse to leave room for user-defined operators.
# Comparisons yield 1.0 (true) or 0.0 (false).
_BINARY_OPS: dict[str, _BinaryOp] = {
    "<": _BinaryOp(5, "left", lambda a, b: float(a < b)),
    "<=": _BinaryOp(5, "left", lambda a, b: float(a <= b)),
    ">": _BinaryOp(5, "left", lambda a, b: float(a > b)),
    ">=": _BinaryOp(5, "left", lambda a, b: float(a >= b)),
    "==": _BinaryOp(5, "left", lambda a, b: float(a == b)),
    "!=": _BinaryOp(5, "left", lambda a, b: float(a != b)),
    "+": _BinaryOp(10, "left", lambda a, b: a + b),
    "-": _BinaryOp(10, "left", lambda a, b: a - b),
    "*": _BinaryOp(20, "left", lambda a, b: a * b),
    "/": _BinaryOp(20, "left", lambda a, b: a / b),
    "%": _BinaryOp(20, "left", lambda a, b: a % b),
    "^": _BinaryOp(30, "right", _power),
    "**": _BinaryOp(30, "right", _power),
}

# Operand of unary minus is parsed at this precedence: operators with
# precedence >= this value bind inside the negation, others do not.
_UNARY_MINUS_PREC = 25

_PUNCTUATION = ("(", ")", ",")


# --------------------------------------------------------------------------
# Built-in functions and constants
# --------------------------------------------------------------------------

def _sqrt(x: float) -> float:
    if x < 0:
        raise ValueError(f"sqrt of negative number {x!r}")
    return math.sqrt(x)


# name -> (callable, min_args, max_args or None for unbounded)
_FUNCTIONS: dict[str, tuple[Callable[..., float], int, int | None]] = {
    "min": (min, 1, None),
    "max": (max, 1, None),
    "sqrt": (_sqrt, 1, 1),
    "abs": (abs, 1, 1),
}

_CONSTANTS: dict[str, float] = {
    "pi": math.pi,
    "e": math.e,
}


# --------------------------------------------------------------------------
# Tokenizer
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class _Token:
    kind: str  # "number" | "ident" | "op" | "punct" | "eof"
    value: str
    position: int


def _build_token_re() -> re.Pattern[str]:
    # Longest operator symbols first so that e.g. ``**`` wins over ``*``.
    symbols = sorted(_BINARY_OPS, key=len, reverse=True)
    op_alt = "|".join(re.escape(s) for s in symbols)
    punct_alt = "|".join(re.escape(p) for p in _PUNCTUATION)
    return re.compile(
        rf"(?P<ws>\s+)"
        rf"|(?P<number>\d+\.\d*|\.\d+|\d+)"
        rf"|(?P<ident>[A-Za-z_][A-Za-z0-9_]*)"
        rf"|(?P<op>{op_alt})"
        rf"|(?P<punct>{punct_alt})"
    )


_TOKEN_RE = _build_token_re()


def _tokenize(text: str) -> list[_Token]:
    tokens: list[_Token] = []
    pos = 0
    while pos < len(text):
        m = _TOKEN_RE.match(text, pos)
        if m is None:
            raise ExprError(f"unexpected character {text[pos]!r}", pos)
        kind = m.lastgroup
        assert kind is not None
        if kind != "ws":
            tokens.append(_Token(kind, m.group(), pos))
        pos = m.end()
    tokens.append(_Token("eof", "", len(text)))
    return tokens


# --------------------------------------------------------------------------
# Parser / evaluator
# --------------------------------------------------------------------------

class _Parser:
    def __init__(self, tokens: list[_Token], variables: Mapping[str, object]):
        self._tokens = tokens
        self._i = 0
        self._vars = variables

    # -- token helpers -------------------------------------------------
    def _peek(self) -> _Token:
        return self._tokens[self._i]

    def _advance(self) -> _Token:
        tok = self._tokens[self._i]
        self._i += 1
        return tok

    def _accept(self, kind: str, *values: str) -> _Token | None:
        tok = self._peek()
        if tok.kind == kind and tok.value in values:
            self._advance()
            return tok
        return None

    def _expect_punct(self, value: str) -> None:
        if self._accept("punct", value) is None:
            raise ExprError(f"expected {value!r} but found {self._describe(self._peek())}",
                            self._peek().position)

    @staticmethod
    def _describe(tok: _Token) -> str:
        return "end of input" if tok.kind == "eof" else repr(tok.value)

    # -- grammar -------------------------------------------------------
    def parse(self) -> float:
        value = self._expr(0)
        tok = self._peek()
        if tok.kind != "eof":
            raise ExprError(f"unexpected token {tok.value!r}", tok.position)
        return value

    def _expr(self, min_prec: int) -> float:
        """Precedence climbing: parse a prefix, then fold in operators of precedence >= min_prec."""
        lhs = self._prefix()
        while True:
            tok = self._peek()
            if tok.kind != "op":
                break
            op = _BINARY_OPS[tok.value]
            if op.precedence < min_prec:
                break
            self._advance()
            next_min = op.precedence if op.associativity == "right" else op.precedence + 1
            rhs = self._expr(next_min)
            lhs = self._apply_binary(op, lhs, rhs, tok)
        return lhs

    @staticmethod
    def _apply_binary(op: _BinaryOp, lhs: float, rhs: float, tok: _Token) -> float:
        try:
            return float(op.fn(lhs, rhs))
        except ZeroDivisionError as exc:
            messages = {"/": "division by zero", "%": "modulo by zero"}
            raise ExprError(messages.get(tok.value, str(exc)), tok.position) from exc
        except (OverflowError, ValueError) as exc:
            raise ExprError(f"invalid operation {tok.value!r}: {exc}", tok.position) from exc

    def _prefix(self) -> float:
        if self._accept("op", "-") is not None:
            return -self._expr(_UNARY_MINUS_PREC)
        return self._primary()

    def _primary(self) -> float:
        tok = self._advance()
        if tok.kind == "number":
            return float(tok.value)
        if tok.kind == "ident":
            if self._accept("punct", "(") is not None:
                return self._call(tok)
            if tok.value in self._vars:
                return float(self._vars[tok.value])
            if tok.value in _CONSTANTS:
                return _CONSTANTS[tok.value]
            raise ExprError(f"unknown variable {tok.value!r}", tok.position)
        if tok.kind == "punct" and tok.value == "(":
            inner = self._expr(0)
            self._expect_punct(")")
            return inner
        raise ExprError(f"expected a number, variable or '(' but found {self._describe(tok)}",
                        tok.position)

    def _call(self, name_tok: _Token) -> float:
        """Parse the argument list (opening '(' already consumed) and apply the function."""
        name = name_tok.value
        if name not in _FUNCTIONS:
            raise ExprError(f"unknown function {name!r}", name_tok.position)
        func, min_args, max_args = _FUNCTIONS[name]
        args: list[float] = []
        if self._accept("punct", ")") is None:
            args.append(self._expr(0))
            while self._accept("punct", ",") is not None:
                args.append(self._expr(0))
            self._expect_punct(")")
        if len(args) < min_args or (max_args is not None and len(args) > max_args):
            raise ExprError(f"{name}() takes {_arity_text(min_args, max_args)}, got {len(args)}",
                            name_tok.position)
        try:
            return float(func(*args))
        except (ValueError, OverflowError) as exc:
            raise ExprError(f"{name}(): {exc}", name_tok.position) from exc


def _arity_text(min_args: int, max_args: int | None) -> str:
    if max_args is None:
        return f"at least {min_args} argument(s)"
    if min_args == max_args:
        return f"exactly {min_args} argument(s)"
    return f"{min_args} to {max_args} arguments"


def evaluate(text: str, variables: Mapping[str, object] | None = None) -> float:
    """Evaluate an arithmetic expression and return the result as a float.

    Raises ``ExprError`` (with ``.position``) on any syntax error, unknown name,
    wrong arity, or invalid arithmetic such as division by zero.
    """
    tokens = _tokenize(text)
    return _Parser(tokens, variables or {}).parse()


def evaluate_many(
    texts: list[str], variables: Mapping[str, object] | None = None
) -> list[float | ExprError]:
    """Evaluate each expression against the same variables.

    Returns one entry per input: the value, or the ``ExprError`` instance that
    ``evaluate`` would have raised for that expression.
    """
    results: list[float | ExprError] = []
    for text in texts:
        try:
            results.append(evaluate(text, variables))
        except ExprError as exc:
            results.append(exc)
    return results
