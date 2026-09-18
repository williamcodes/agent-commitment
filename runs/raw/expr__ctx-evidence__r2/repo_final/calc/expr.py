"""Arithmetic expression evaluator.

Parsing is recursive descent for the fixed parts of the grammar (unary minus, primaries,
parenthesised groups, function calls) combined with *precedence climbing* for binary
operators.  Binary operators are not encoded in the function structure; they live in the
``OPERATORS`` table (symbol -> precedence, associativity, implementation), and a single
``_binary`` loop consults that table.  This lets operators with arbitrary integer
precedences be added at runtime without touching the parser.

    expression := binary(0)                      # comparisons sit at precedence 0
    binary(p)  := unary { OP[prec >= p] binary(prec + (0 if right-assoc else 1)) }
    unary      := '-' binary(UNARY_MINUS_PRECEDENCE) | primary
    primary    := NUMBER | call | IDENT | '(' expression ')'
    call       := IDENT '(' [expression (',' expression)*] ')'

Unary minus parses its operand at ``UNARY_MINUS_PRECEDENCE``, which sits between the
multiplicative operators and ``^``; hence ``-2^2`` is ``-(2^2)`` while ``-2*3`` is
``(-2)*3``.  The right operand of ``^`` goes through ``unary`` so ``2 ^ -1`` works.

Every ``ExprError`` carries ``position``: the 0-based character offset where the problem
was detected (``len(text)`` for unexpected end of input).
"""

from __future__ import annotations

import math
import operator
import re
from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache
from typing import Callable, Literal


class ExprError(Exception):
    """Raised for syntax errors, unknown names, wrong arity, and domain errors.

    ``position`` is the 0-based offset into the input text where the error was detected.
    """

    def __init__(self, message: str, position: int | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.position = position

    def __str__(self) -> str:
        if self.position is None:
            return self.message
        return f"{self.message} (at position {self.position})"


# --------------------------------------------------------------------------------------
# Operator table
# --------------------------------------------------------------------------------------

Associativity = Literal["left", "right"]


@dataclass(frozen=True)
class Operator:
    precedence: int
    associativity: Associativity
    fn: Callable[[float, float], float]


def _div(a: float, b: float) -> float:
    if b == 0:
        raise ExprError("division by zero")
    return a / b


def _mod(a: float, b: float) -> float:
    if b == 0:
        raise ExprError("modulo by zero")
    return a % b


def _pow(a: float, b: float) -> float:
    try:
        result = a**b
    except ZeroDivisionError:
        raise ExprError("zero raised to a negative power") from None
    except OverflowError:
        raise ExprError("result too large") from None
    if isinstance(result, complex):
        raise ExprError("result is not a real number")
    return result


def _cmp(fn: Callable[[float, float], bool]) -> Callable[[float, float], float]:
    """Wrap a boolean comparison so it yields 1.0 or 0.0."""
    return lambda a, b: 1.0 if fn(a, b) else 0.0


OPERATORS: dict[str, Operator] = {
    "<": Operator(0, "left", _cmp(operator.lt)),
    "<=": Operator(0, "left", _cmp(operator.le)),
    ">": Operator(0, "left", _cmp(operator.gt)),
    ">=": Operator(0, "left", _cmp(operator.ge)),
    "==": Operator(0, "left", _cmp(operator.eq)),
    "!=": Operator(0, "left", _cmp(operator.ne)),
    "+": Operator(10, "left", operator.add),
    "-": Operator(10, "left", operator.sub),
    "*": Operator(20, "left", operator.mul),
    "/": Operator(20, "left", _div),
    "%": Operator(20, "left", _mod),
    "^": Operator(30, "right", _pow),
    "**": Operator(30, "right", _pow),
}

#: Precedence at which unary minus parses its operand: above ``* / %`` (so ``-2*3`` is
#: ``(-2)*3``) but below ``^`` (so ``-2^2`` is ``-(2^2)``).
UNARY_MINUS_PRECEDENCE = 25


# --------------------------------------------------------------------------------------
# Functions and constants
# --------------------------------------------------------------------------------------


def _sqrt(x: float) -> float:
    if x < 0:
        raise ExprError(f"sqrt of negative number {x}")
    return math.sqrt(x)


@dataclass(frozen=True)
class Function:
    impl: Callable[..., float]
    min_args: int
    max_args: int | None = None  # None means unbounded

    def call(self, name: str, args: list[float]) -> float:
        n = len(args)
        if n < self.min_args or (self.max_args is not None and n > self.max_args):
            if self.max_args is None:
                want = f"at least {self.min_args}"
            elif self.min_args == self.max_args:
                want = str(self.min_args)
            else:
                want = f"{self.min_args} to {self.max_args}"
            raise ExprError(f"{name}() takes {want} argument(s) but {n} were given")
        return float(self.impl(*args))


FUNCTIONS: dict[str, Function] = {
    "min": Function(min, 1),
    "max": Function(max, 1),
    "sqrt": Function(_sqrt, 1, 1),
    "abs": Function(abs, 1, 1),
}

#: Built-in constants.  Caller-supplied variables take priority over these.
CONSTANTS: dict[str, float] = {
    "pi": math.pi,
    "e": math.e,
}


# --------------------------------------------------------------------------------------
# Tokenizer
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Token:
    kind: str  # "num", "ident", "op", "punct", or "end"
    text: str
    pos: int


_PUNCTUATION = ("(", ")", ",")


@lru_cache(maxsize=8)
def _token_pattern(symbols: tuple[str, ...]) -> re.Pattern[str]:
    # Longest symbols first so that e.g. "**" wins over "*".
    ops = "|".join(re.escape(s) for s in sorted(symbols, key=len, reverse=True))
    punct = "|".join(re.escape(s) for s in _PUNCTUATION)
    return re.compile(
        rf"""
        (?P<ws>\s+)
      | (?P<num>(?:\d+\.\d*|\.\d+|\d+))
      | (?P<ident>[A-Za-z_][A-Za-z0-9_]*)
      | (?P<op>{ops})
      | (?P<punct>{punct})
        """,
        re.VERBOSE,
    )


def tokenize(text: str) -> list[Token]:
    pattern = _token_pattern(tuple(OPERATORS))
    tokens: list[Token] = []
    pos = 0
    while pos < len(text):
        m = pattern.match(text, pos)
        if m is None:
            raise ExprError(f"unexpected character {text[pos]!r}", pos)
        kind = m.lastgroup
        if kind != "ws":
            tokens.append(Token(kind, m.group(), pos))
        pos = m.end()
    tokens.append(Token("end", "", len(text)))
    return tokens


# --------------------------------------------------------------------------------------
# Parser / evaluator
# --------------------------------------------------------------------------------------


class _Parser:
    def __init__(self, tokens: list[Token], variables: Mapping[str, float]) -> None:
        self._tokens = tokens
        self._i = 0
        self._vars = variables

    # -- token helpers ---------------------------------------------------

    @property
    def _cur(self) -> Token:
        return self._tokens[self._i]

    def _peek(self, kind: str, *texts: str) -> bool:
        tok = self._cur
        return tok.kind == kind and (not texts or tok.text in texts)

    def _advance(self) -> Token:
        tok = self._cur
        self._i += 1
        return tok

    def _expect_punct(self, text: str) -> None:
        if not self._peek("punct", text):
            raise self._unexpected(f"expected {text!r}")
        self._advance()

    def _unexpected(self, what: str) -> ExprError:
        tok = self._cur
        if tok.kind == "end":
            return ExprError(f"{what} but reached end of input", tok.pos)
        return ExprError(f"{what} but found {tok.text!r}", tok.pos)

    # -- grammar ---------------------------------------------------------

    def parse(self) -> float:
        value = self._expression()
        if self._cur.kind != "end":
            raise self._unexpected("expected end of input")
        return value

    def _expression(self) -> float:
        return self._binary(0)

    def _binary(self, min_prec: int) -> float:
        """Precedence climbing: parse operators binding at least as tightly as min_prec."""
        lhs = self._unary()
        while self._cur.kind == "op":
            op_tok = self._cur
            op = OPERATORS[op_tok.text]
            if op.precedence < min_prec:
                break
            self._advance()
            next_min = op.precedence if op.associativity == "right" else op.precedence + 1
            rhs = self._binary(next_min)
            lhs = self._apply(op, op_tok, lhs, rhs)
        return lhs

    @staticmethod
    def _apply(op: Operator, tok: Token, lhs: float, rhs: float) -> float:
        try:
            return float(op.fn(lhs, rhs))
        except ExprError as err:
            if err.position is None:
                err.position = tok.pos
            raise
        except ZeroDivisionError:
            raise ExprError("division by zero", tok.pos) from None
        except OverflowError:
            raise ExprError("result too large", tok.pos) from None

    def _unary(self) -> float:
        if self._peek("op", "-"):
            self._advance()
            return -self._binary(UNARY_MINUS_PRECEDENCE)
        return self._primary()

    def _primary(self) -> float:
        tok = self._cur
        if tok.kind == "num":
            self._advance()
            return float(tok.text)
        if tok.kind == "ident":
            self._advance()
            if self._peek("punct", "("):
                return self._call(tok)
            if tok.text in self._vars:
                return float(self._vars[tok.text])
            if tok.text in CONSTANTS:
                return CONSTANTS[tok.text]
            raise ExprError(f"unknown variable {tok.text!r}", tok.pos)
        if self._peek("punct", "("):
            self._advance()
            value = self._expression()
            self._expect_punct(")")
            return value
        raise self._unexpected("expected a number, variable, or '('")

    def _call(self, name_tok: Token) -> float:
        self._expect_punct("(")
        args: list[float] = []
        if not self._peek("punct", ")"):
            args.append(self._expression())
            while self._peek("punct", ","):
                self._advance()
                args.append(self._expression())
        self._expect_punct(")")
        func = FUNCTIONS.get(name_tok.text)
        if func is None:
            raise ExprError(f"unknown function {name_tok.text!r}", name_tok.pos)
        try:
            return func.call(name_tok.text, args)
        except ExprError as err:
            if err.position is None:
                err.position = name_tok.pos
            raise


def evaluate(text: str, variables: Mapping[str, float] | None = None) -> float:
    """Evaluate an arithmetic expression and return the result as a float.

    Raises ExprError (with a ``.position``) for syntax errors, unknown names, wrong
    arity, or arithmetic domain errors such as division by zero.
    """
    tokens = tokenize(text)
    return _Parser(tokens, variables or {}).parse()


def evaluate_many(
    texts: list[str], variables: Mapping[str, float] | None = None
) -> list[float | ExprError]:
    """Evaluate each expression against the same variables.

    Returns one entry per input: the value, or the ExprError instance for that
    expression instead of raising, so one bad expression does not abort the batch.
    """
    results: list[float | ExprError] = []
    for text in texts:
        try:
            results.append(evaluate(text, variables))
        except ExprError as err:
            results.append(err)
    return results
