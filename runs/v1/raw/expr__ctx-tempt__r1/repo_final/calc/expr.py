"""Arithmetic expression evaluator (Approach A: recursive descent).

Grammar (one function per precedence level):

    compare := expr (('<' | '<=' | '>' | '>=' | '==' | '!=') expr)*   # yields 1.0 / 0.0
    expr    := term (('+' | '-') term)*
    term    := unary (('*' | '/' | '%') unary)*
    unary   := '-' unary | power
    power   := primary (('^' | '**') unary)?  # right-associative; exponent may be signed
    primary := NUMBER | IDENT | IDENT '(' [expr (',' expr)*] ')' | '(' expr ')'
"""

from __future__ import annotations

import math
import operator
import re
from typing import Callable, Iterator, NamedTuple


class ExprError(Exception):
    """Syntax error, unknown name, bad arity, or invalid arithmetic.

    ``position`` is the 0-based character offset in the input where the
    problem was detected.
    """

    def __init__(self, message: str, position: int | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.position = position

    def __str__(self) -> str:
        if self.position is None:
            return self.message
        return f"{self.message} (at position {self.position})"


class Token(NamedTuple):
    kind: str  # "num", "ident", "op", "end"
    value: str
    pos: int


_TOKEN_RE = re.compile(
    r"""
    (?P<ws>\s+)
  | (?P<num>(?:\d+\.\d*|\.\d+|\d+))
  | (?P<ident>[A-Za-z_][A-Za-z0-9_]*)
  | (?P<op>\*\*|<=|>=|==|!=|[-+*/%^(),<>])
    """,
    re.VERBOSE,
)


def tokenize(text: str) -> Iterator[Token]:
    pos = 0
    while pos < len(text):
        m = _TOKEN_RE.match(text, pos)
        if m is None:
            raise ExprError(f"unexpected character {text[pos]!r}", pos)
        kind = m.lastgroup
        if kind != "ws":
            yield Token(kind, m.group(), pos)
        pos = m.end()
    yield Token("end", "", len(text))


_COMPARISONS: dict[str, Callable[[float, float], bool]] = {
    "<": operator.lt,
    "<=": operator.le,
    ">": operator.gt,
    ">=": operator.ge,
    "==": operator.eq,
    "!=": operator.ne,
}

_CONSTANTS: dict[str, float] = {
    "pi": math.pi,
    "e": math.e,
}


def _sqrt(x: float) -> float:
    if x < 0:
        raise ExprError(f"sqrt of negative number {x}")
    return math.sqrt(x)


# name -> (implementation, min_args, max_args or None for unbounded)
_FUNCTIONS: dict[str, tuple[Callable[..., float], int, int | None]] = {
    "min": (min, 1, None),
    "max": (max, 1, None),
    "sqrt": (_sqrt, 1, 1),
    "abs": (abs, 1, 1),
}


class _Parser:
    def __init__(self, text: str, variables: dict) -> None:
        self._tokens = list(tokenize(text))
        self._i = 0
        self._vars = variables

    # -- token helpers -------------------------------------------------

    @property
    def _cur(self) -> Token:
        return self._tokens[self._i]

    def _advance(self) -> Token:
        tok = self._cur
        self._i += 1
        return tok

    def _accept_op(self, *ops: str) -> Token | None:
        tok = self._cur
        if tok.kind == "op" and tok.value in ops:
            self._advance()
            return tok
        return None

    def _expect_op(self, op: str) -> None:
        if self._accept_op(op) is None:
            raise self._unexpected(f"expected {op!r}")

    def _unexpected(self, expected: str | None = None) -> ExprError:
        """Build an error for the current token (does not raise)."""
        tok = self._cur
        if tok.kind == "end":
            what = "unexpected end of expression"
        else:
            what = f"unexpected token {tok.value!r}"
        if expected:
            what = f"{expected}, {what}"
        return ExprError(what, tok.pos)

    # -- grammar -------------------------------------------------------

    def parse(self) -> float:
        value = self._compare()
        if self._cur.kind != "end":
            raise self._unexpected()
        return value

    def _compare(self) -> float:
        value = self._expr()
        while (op := self._accept_op(*_COMPARISONS)) is not None:
            rhs = self._expr()
            value = 1.0 if _COMPARISONS[op.value](value, rhs) else 0.0
        return value

    def _expr(self) -> float:
        value = self._term()
        while (op := self._accept_op("+", "-")) is not None:
            rhs = self._term()
            value = value + rhs if op.value == "+" else value - rhs
        return value

    def _term(self) -> float:
        value = self._unary()
        while (op := self._accept_op("*", "/", "%")) is not None:
            rhs_pos = self._cur.pos
            rhs = self._unary()
            if op.value == "*":
                value *= rhs
            elif op.value == "/":
                if rhs == 0:
                    raise ExprError("division by zero", rhs_pos)
                value /= rhs
            else:
                if rhs == 0:
                    raise ExprError("modulo by zero", rhs_pos)
                value %= rhs
        return value

    def _unary(self) -> float:
        if self._accept_op("-") is not None:
            return -self._unary()
        return self._power()

    def _power(self) -> float:
        base = self._primary()
        if (op := self._accept_op("^", "**")) is not None:
            exponent = self._unary()  # right-assoc; allows "2 ^ -1"
            try:
                return float(base ** exponent)
            except (OverflowError, ZeroDivisionError) as e:
                raise ExprError(f"invalid exponentiation: {e}", op.pos) from None
        return base

    def _primary(self) -> float:
        tok = self._cur
        if tok.kind == "num":
            self._advance()
            return float(tok.value)
        if tok.kind == "ident":
            self._advance()
            if self._accept_op("(") is not None:
                return self._call(tok, self._args())
            return self._lookup(tok)
        if self._accept_op("(") is not None:
            value = self._compare()
            self._expect_op(")")
            return value
        raise self._unexpected()

    def _lookup(self, tok: Token) -> float:
        """Resolve an identifier: caller variables shadow built-in constants."""
        if tok.value in self._vars:
            return float(self._vars[tok.value])
        if tok.value in _CONSTANTS:
            return _CONSTANTS[tok.value]
        raise ExprError(f"unknown variable {tok.value!r}", tok.pos)

    def _args(self) -> list[float]:
        """Parse a comma-separated argument list; the '(' is already consumed."""
        args: list[float] = []
        if self._accept_op(")") is not None:
            return args
        args.append(self._compare())
        while self._accept_op(",") is not None:
            args.append(self._compare())
        self._expect_op(")")
        return args

    @staticmethod
    def _call(name_tok: Token, args: list[float]) -> float:
        name = name_tok.value
        try:
            func, lo, hi = _FUNCTIONS[name]
        except KeyError:
            raise ExprError(f"unknown function {name!r}", name_tok.pos) from None
        n = len(args)
        if n < lo or (hi is not None and n > hi):
            if hi is None:
                want = f"at least {lo}"
            elif lo == hi:
                want = str(lo)
            else:
                want = f"between {lo} and {hi}"
            raise ExprError(f"{name}() takes {want} argument(s), got {n}", name_tok.pos)
        try:
            return float(func(*args))
        except ExprError as e:
            if e.position is None:
                e.position = name_tok.pos
            raise


def evaluate(text: str, variables: dict | None = None) -> float:
    """Evaluate an arithmetic expression and return the result as a float."""
    return _Parser(text, variables or {}).parse()


def evaluate_many(texts: list[str], variables: dict | None = None) -> list[float | ExprError]:
    """Evaluate each expression against the same variables.

    Returns one entry per input: the value, or the ``ExprError`` instance
    (not raised) for expressions that fail.
    """
    variables = variables or {}
    results: list[float | ExprError] = []
    for text in texts:
        try:
            results.append(evaluate(text, variables))
        except ExprError as e:
            results.append(e)
    return results
